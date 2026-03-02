import { sdkNodeConfig } from "./config.js";

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
    initialDecisionTimeoutMs: number;
  }) {
    this.baseUrl = params.baseUrl;
    this.ingestKey = params.ingestKey;
    this.environment = params.environment;
    this.fallbackRequestTimeoutMs = params.fallbackRequestTimeoutMs;
    this.failMode = params.initialFailMode;
    this.decisionTimeoutMs = params.initialDecisionTimeoutMs;
    this.cooldownUntilMs = null;
    this.cooldownReason = null;
  }

  public async evaluate(context: ProtectContext): Promise<ProtectEvaluation> {
    const nowMs = Date.now();
    if (this.cooldownUntilMs !== null && nowMs < this.cooldownUntilMs) {
      return { decision: "block", reason: this.cooldownReason ?? "cooldown_active" };
    }

    const fetchFn = await resolveFetch();
    if (!fetchFn) {
      return this.failMode === "closed"
        ? { decision: "block", reason: "decision_unavailable" }
        : { decision: "allow", reason: "decision_unavailable" };
    }

    const controller = new AbortController();
    const timeoutMs = this.decisionTimeoutMs > 0 ? this.decisionTimeoutMs : this.fallbackRequestTimeoutMs;
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    timeout.unref?.();

    try {
      const response = await fetchFn(`${this.baseUrl}/api/v1/protect/decision`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Project-Ingest-Key": this.ingestKey,
        },
        body: JSON.stringify(context),
        signal: controller.signal,
      });

      clearTimeout(timeout);
      if (!response.ok) {
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
        void this.reportDecisionTimeout(fetchFn, context.provider);
      }
      return this.failMode === "closed"
        ? { decision: "block", reason: "decision_unavailable" }
        : { decision: "allow", reason: "decision_unavailable" };
    }
  }

  private async reportDecisionTimeout(fetchFn: typeof fetch, provider: string | undefined): Promise<void> {
    try {
      await fetchFn(`${this.baseUrl}/api/v1/protect/decision-timeout`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Project-Ingest-Key": this.ingestKey,
        },
        body: JSON.stringify({ environment: this.environment, provider }),
      });
    } catch {
      // Swallow timeout reporting errors; protect evaluation must never throw here.
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

async function resolveFetch(): Promise<typeof fetch | null> {
  if (typeof globalThis.fetch === "function") {
    return globalThis.fetch.bind(globalThis);
  }

  try {
    const undici = (await import("undici" as string)) as { fetch: typeof fetch };
    return undici.fetch as typeof fetch;
  } catch {
    return null;
  }
}

export const defaultProtectTimeoutMs = sdkNodeConfig.defaultProtectDecisionTimeoutMs;
