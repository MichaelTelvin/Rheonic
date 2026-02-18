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
}

export interface ProtectEvaluation {
  decision: ProtectDecision;
  reason: string;
}

export class LLMTBGBlockedError extends Error {
  public readonly reason: string;

  public constructor(reason: string) {
    super(`Request blocked by LLMTokenBurnGuard: ${reason}`);
    this.name = "LLMTBGBlockedError";
    this.reason = reason;
  }
}

export class ProtectEngine {
  private readonly baseUrl: string;
  private readonly ingestKey: string;
  private readonly fallbackRequestTimeoutMs: number;
  private failMode: ProtectFailMode;
  private decisionTimeoutMs: number;

  public constructor(params: {
    baseUrl: string;
    ingestKey: string;
    fallbackRequestTimeoutMs: number;
    initialFailMode: ProtectFailMode;
    initialDecisionTimeoutMs: number;
  }) {
    this.baseUrl = params.baseUrl;
    this.ingestKey = params.ingestKey;
    this.fallbackRequestTimeoutMs = params.fallbackRequestTimeoutMs;
    this.failMode = params.initialFailMode;
    this.decisionTimeoutMs = params.initialDecisionTimeoutMs;
  }

  public async evaluate(context: ProtectContext): Promise<ProtectEvaluation> {
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
      return { decision, reason };
    } catch {
      clearTimeout(timeout);
      return this.failMode === "closed"
        ? { decision: "block", reason: "decision_unavailable" }
        : { decision: "allow", reason: "decision_unavailable" };
    }
  }
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
