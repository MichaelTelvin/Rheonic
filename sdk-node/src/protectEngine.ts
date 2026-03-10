import { sdkNodeConfig } from "./config.js";
import { randomUUID } from "node:crypto";
import { requestJson } from "./httpTransport.js";

export type ProtectDecision = "allow" | "warn" | "block";
export type ProtectFailMode = "open" | "closed";

export interface ProtectContext {
  provider: string;
  model?: string | null;
  feature?: string;
  max_output_tokens?: number;
  input_tokens_estimate?: number;
}

interface ProtectDecisionResponse {
  decision?: unknown;
  reason?: unknown;
  fail_mode?: unknown;
  protect_decision_timeout_ms?: unknown;
  blocked_until?: unknown;
  snapshot?: unknown;
  apply_clamp_enabled?: unknown;
  clamp?: unknown;
}

export interface ProtectEvaluation {
  decision: ProtectDecision;
  reason: string;
  snapshot?: Record<string, unknown>;
  applyClampEnabled?: boolean;
  clamp?: {
    recommended_max_output_tokens: number;
    applied: boolean;
  };
}

export class RHEONICBlockedError extends Error {
  public readonly reason: string;

  public constructor(reason: string) {
    super(`Request blocked by Rheonic: ${reason}`);
    this.name = "RHEONICBlockedError";
    this.reason = reason;
  }
}

export class ProtectEngine {
  private readonly baseUrl: string;
  private readonly ingestKey: string;
  private readonly environment: string;
  private readonly fallbackRequestTimeoutMs: number;
  private readonly debugLog?: (message: string, meta?: Record<string, unknown>) => void;
  private failMode: ProtectFailMode;
  private decisionTimeoutMs: number;
  private cooldownUntilMs: number | null;
  private cooldownReason: string | null;

  public constructor(params: {
    baseUrl: string;
    ingestKey: string;
    environment: string;
    fallbackRequestTimeoutMs: number;
    initialFailMode: ProtectFailMode;
    initialDecisionTimeoutMs?: number;
    debugLog?: (message: string, meta?: Record<string, unknown>) => void;
  }) {
    this.baseUrl = params.baseUrl;
    this.ingestKey = params.ingestKey;
    this.environment = params.environment;
    this.fallbackRequestTimeoutMs = params.fallbackRequestTimeoutMs;
    this.debugLog = params.debugLog;
    this.failMode = params.initialFailMode;
    this.decisionTimeoutMs =
      typeof params.initialDecisionTimeoutMs === "number" && Number.isFinite(params.initialDecisionTimeoutMs) && params.initialDecisionTimeoutMs > 0
        ? Math.floor(params.initialDecisionTimeoutMs)
        : sdkNodeConfig.internalProtectDecisionTimeoutMs;
    this.cooldownUntilMs = null;
    this.cooldownReason = null;
  }

  public async evaluate(context: ProtectContext): Promise<ProtectEvaluation> {
    const nowMs = Date.now();
    if (this.cooldownUntilMs !== null && nowMs < this.cooldownUntilMs) {
      this.debugLog?.("Protect preflight blocked locally from cached cooldown", {
        provider: context.provider,
        decision: "block",
        reason: this.cooldownReason ?? "cooldown_active",
      });
      return { decision: "block", reason: this.cooldownReason ?? "cooldown_active" };
    }

    const controller = new AbortController();
    const timeoutMs = this.decisionTimeoutMs > 0 ? this.decisionTimeoutMs : this.fallbackRequestTimeoutMs;
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    timeout.unref?.();
    const startedAt = Date.now();
    const requestId = randomUUID();

    try {
      const response = await requestJson(`${this.baseUrl}/api/v1/protect/decision`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Project-Ingest-Key": this.ingestKey,
          "X-Rheonic-Protect-Request-Id": requestId,
        },
        body: JSON.stringify(context),
        signal: controller.signal,
      });

      clearTimeout(timeout);
      if (!response.ok) {
        this.debugLog?.("Protect preflight returned non-success status", {
          provider: context.provider,
          status_code: response.status,
          latency_ms: Date.now() - startedAt,
        });
        void this.reportDecisionUnavailable(context.provider, requestId);
        return this.failMode === "closed"
          ? { decision: "block", reason: "decision_unavailable" }
          : { decision: "allow", reason: "decision_unavailable" };
      }

      const parsed = (await response.json()) as ProtectDecisionResponse;
      const decision = parseDecision(parsed.decision);

      const reason = typeof parsed.reason === "string" ? parsed.reason : "ok";
      const failMode = parseFailMode(parsed.fail_mode);
      if (failMode) {
        this.failMode = failMode;
      }
      const decisionTimeout = Number(parsed.protect_decision_timeout_ms);
      if (Number.isFinite(decisionTimeout) && decisionTimeout > 0) {
        this.decisionTimeoutMs = decisionTimeout;
      }
      const blockedUntilMs = parseBlockedUntilMs(parsed.blocked_until);
      if (blockedUntilMs !== null && blockedUntilMs > Date.now()) {
        this.cooldownUntilMs = blockedUntilMs;
        this.cooldownReason = "cooldown_active";
      } else if (this.cooldownUntilMs !== null && Date.now() >= this.cooldownUntilMs) {
        this.cooldownUntilMs = null;
        this.cooldownReason = null;
      }
      this.debugLog?.("Protect preflight completed", {
        provider: context.provider,
        decision,
        reason,
        latency_ms: Date.now() - startedAt,
        timeout_ms: this.decisionTimeoutMs,
      });
      return {
        decision,
        reason,
        snapshot: parseSnapshot(parsed.snapshot),
        applyClampEnabled: typeof parsed.apply_clamp_enabled === "boolean" ? parsed.apply_clamp_enabled : undefined,
        clamp: parseClamp(parsed.clamp),
      };
    } catch (error) {
      clearTimeout(timeout);
      if (isAbortError(error)) {
        this.debugLog?.("Protect preflight timed out", {
          provider: context.provider,
          latency_ms: Date.now() - startedAt,
          timeout_ms: timeoutMs,
        });
        void this.reportDecisionTimeout(context.provider, requestId);
      } else {
        this.debugLog?.("Protect preflight failed", {
          provider: context.provider,
          latency_ms: Date.now() - startedAt,
          error_type: extractErrorType(error),
        });
        void this.reportDecisionUnavailable(context.provider, requestId);
      }
      return this.failMode === "closed"
        ? { decision: "block", reason: "decision_unavailable" }
        : { decision: "allow", reason: "decision_unavailable" };
    }
  }

  public async bootstrap(): Promise<void> {
    try {
      const response = await requestJson(`${this.baseUrl}/api/v1/protect/config`, {
        method: "GET",
        headers: {
          "X-Project-Ingest-Key": this.ingestKey,
        },
      });
      if (!response.ok) {
        return;
      }
      const parsed = (await response.json()) as {
        protect_fail_mode?: unknown;
        protect_decision_timeout_ms?: unknown;
      };
      const failMode = parseFailMode(parsed.protect_fail_mode);
      if (failMode) {
        this.failMode = failMode;
      }
      const decisionTimeout = Number(parsed.protect_decision_timeout_ms);
      if (Number.isFinite(decisionTimeout) && decisionTimeout > 0) {
        this.decisionTimeoutMs = Math.floor(decisionTimeout);
      }
    } catch {
      // Best effort only; keep local defaults if bootstrap fails.
    }
  }

  private async reportDecisionTimeout(provider: string | undefined, requestId: string): Promise<void> {
    try {
      await requestJson(`${this.baseUrl}/api/v1/protect/decision-timeout`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Project-Ingest-Key": this.ingestKey,
          "X-Rheonic-Protect-Request-Id": requestId,
        },
        body: JSON.stringify({ environment: this.environment, provider, request_id: requestId }),
      });
    } catch {
      // Swallow timeout reporting errors; protect evaluation must never throw here.
    }
  }

  private async reportDecisionUnavailable(provider: string | undefined, requestId: string): Promise<void> {
    try {
      await requestJson(`${this.baseUrl}/api/v1/protect/decision-unavailable`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Project-Ingest-Key": this.ingestKey,
          "X-Rheonic-Protect-Request-Id": requestId,
        },
        body: JSON.stringify({ environment: this.environment, provider, request_id: requestId }),
      });
    } catch {
      // Swallow unavailable reporting errors; protect evaluation must never throw here.
    }
  }
}

function parseClamp(value: unknown): { recommended_max_output_tokens: number; applied: boolean } | undefined {
  if (!value || typeof value !== "object") {
    return undefined;
  }
  const candidate = value as { recommended_max_output_tokens?: unknown; applied?: unknown };
  if (typeof candidate.recommended_max_output_tokens !== "number" || candidate.recommended_max_output_tokens < 1) {
    return undefined;
  }
  return {
    recommended_max_output_tokens: Math.floor(candidate.recommended_max_output_tokens),
    applied: typeof candidate.applied === "boolean" ? candidate.applied : false,
  };
}

function parseSnapshot(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return undefined;
  }
  return value as Record<string, unknown>;
}

function parseBlockedUntilMs(value: unknown): number | null {
  if (typeof value !== "string" || !value) {
    return null;
  }
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

function parseDecision(value: unknown): ProtectDecision {
  if (value === "warn" || value === "block" || value === "allow") {
    return value;
  }
  return "allow";
}

function parseFailMode(value: unknown): ProtectFailMode | null {
  if (value === "open" || value === "closed") {
    return value;
  }
  return null;
}

function isAbortError(value: unknown): boolean {
  return typeof value === "object" && value !== null && "name" in value && (value as { name?: unknown }).name === "AbortError";
}

function extractErrorType(value: unknown): string {
  if (value && typeof value === "object" && "name" in value) {
    const maybeName = (value as { name?: unknown }).name;
    if (typeof maybeName === "string" && maybeName.length > 0) {
      return maybeName;
    }
  }
  return "unknown";
}

export const defaultProtectTimeoutMs = sdkNodeConfig.internalProtectDecisionTimeoutMs;
