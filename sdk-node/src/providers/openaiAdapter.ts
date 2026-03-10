import type { Client } from "../client.js";
import { buildEvent } from "../eventBuilder.js";
import { validateProviderModel } from "../providerModelValidation.js";
import { RHEONICBlockedError, type ProtectEvaluation } from "../protectEngine.js";
import { estimateInputTokensFromRequest } from "../tokenEstimator.js";

export interface OpenAIInstrumentationOptions {
  client: Client;
  environment?: string;
  endpoint?: string;
  feature?: string;
}

let estimatorOverrideForTests: ((payload: unknown) => number | null) | null = null;

export function __setInputTokenEstimatorForTests(
  estimator: ((payload: unknown) => number | null) | null,
): void {
  estimatorOverrideForTests = estimator;
}

export function instrumentOpenAI<T extends Record<string, any>>(openaiClient: T, options: OpenAIInstrumentationOptions): T {
  const targetCreate = openaiClient?.chat?.completions?.create;
  if (typeof targetCreate !== "function") {
    return openaiClient;
  }

  const originalCreate = targetCreate.bind(openaiClient.chat.completions);

  openaiClient.chat.completions.create = async (...args: unknown[]) => {
    const startedAt = Date.now();
    const model = extractRequestedModel(args);
    validateProviderModel("openai", model);
    const requestPayload = extractRequestPayload(args);
    const tokenEstimateStartedAt = Date.now();
    const estimatedInputTokens = requestPayload
      ? (estimatorOverrideForTests
          ? estimatorOverrideForTests(requestPayload)
          : estimateInputTokensFromRequest(requestPayload))
      : null;
    options.client.debugLog("Protect token estimation completed", {
      provider: "openai",
      model,
      latency_ms: Date.now() - tokenEstimateStartedAt,
      estimated_input_tokens: estimatedInputTokens ?? undefined,
    });
    const protectPayload: {
      provider: string;
      model: string | null;
      environment?: string;
      feature?: string;
      max_output_tokens?: number;
      input_tokens_estimate?: number;
    } = {
      provider: "openai",
      model,
      environment: options.environment ?? options.client.environment,
      feature: options.feature,
      max_output_tokens: extractMaxOutputTokens(args),
    };
    if (typeof estimatedInputTokens === "number") {
      protectPayload.input_tokens_estimate = estimatedInputTokens;
    }
    const protectDecision = await options.client.evaluateProtectDecision({
      ...protectPayload,
    });
    if (protectDecision.decision === "block") {
      throw new RHEONICBlockedError(protectDecision.reason);
    }
    const callArgs = maybeApplyOpenAIClamp(args, protectDecision);
    markClampAppliedIfChanged(protectDecision, extractMaxOutputTokens(args), extractMaxOutputTokens(callArgs));

    try {
      const response = await originalCreate(...callArgs);
      void options.client.captureEvent(
        buildEvent({
          provider: "openai",
          model: extractResponseModel(response) ?? model,
          environment: options.environment ?? options.client.environment,
          request: {
            endpoint: options.endpoint,
            feature: options.feature,
            protect_decision: protectDecision.decision === "warn" ? "warn" : undefined,
            protect_reason: protectDecision.decision === "warn" ? protectDecision.reason : undefined,
          },
          response: {
            latency_ms: Date.now() - startedAt,
            total_tokens: extractTotalTokens(response),
            http_status: 200,
          },
        }),
      );
      return response;
    } catch (error) {
      void options.client.captureEvent(
        buildEvent({
          provider: "openai",
          model,
          environment: options.environment ?? options.client.environment,
          request: {
            endpoint: options.endpoint,
            feature: options.feature,
            protect_decision: protectDecision.decision === "warn" ? "warn" : undefined,
            protect_reason: protectDecision.decision === "warn" ? protectDecision.reason : undefined,
          },
          response: {
            latency_ms: Date.now() - startedAt,
            error_type: extractErrorType(error),
            http_status: extractHttpStatus(error),
          },
        }),
      );
      throw error;
    }
  };

  return openaiClient;
}

function extractRequestedModel(args: unknown[]): string | null {
  const firstArg = args[0];
  if (firstArg && typeof firstArg === "object" && "model" in firstArg) {
    const maybeModel = (firstArg as { model?: unknown }).model;
    return typeof maybeModel === "string" ? maybeModel : null;
  }
  return null;
}

function extractRequestPayload(args: unknown[]): Record<string, unknown> | null {
  const firstArg = args[0];
  if (!firstArg || typeof firstArg !== "object") {
    return null;
  }
  return firstArg as Record<string, unknown>;
}

function extractMaxOutputTokens(args: unknown[]): number | undefined {
  const firstArg = args[0];
  if (!firstArg || typeof firstArg !== "object") {
    return undefined;
  }
  if ("max_tokens" in firstArg && typeof (firstArg as { max_tokens?: unknown }).max_tokens === "number") {
    return (firstArg as { max_tokens: number }).max_tokens;
  }
  if ("max_output_tokens" in firstArg && typeof (firstArg as { max_output_tokens?: unknown }).max_output_tokens === "number") {
    return (firstArg as { max_output_tokens: number }).max_output_tokens;
  }
  return undefined;
}

function maybeApplyOpenAIClamp(args: unknown[], decision: ProtectEvaluation): unknown[] {
  if (decision.decision !== "warn" || decision.reason !== "near_cap") {
    return args;
  }
  if (!decision.applyClampEnabled) {
    return args;
  }
  const recommended = decision.clamp?.recommended_max_output_tokens;
  if (typeof recommended !== "number" || recommended < 1) {
    return args;
  }
  const firstArg = args[0];
  if (!firstArg || typeof firstArg !== "object") {
    return args;
  }
  const payload = { ...(firstArg as Record<string, unknown>) };
  let updated = false;
  const maxTokens = payload.max_tokens;
  if (typeof maxTokens === "number") {
    payload.max_tokens = Math.min(maxTokens, recommended);
    updated = true;
  }
  const maxOutputTokens = payload.max_output_tokens;
  if (typeof maxOutputTokens === "number") {
    payload.max_output_tokens = Math.min(maxOutputTokens, recommended);
    updated = true;
  }
  if (!updated) {
    payload.max_tokens = recommended;
  }
  const nextArgs = [...args];
  nextArgs[0] = payload;
  return nextArgs;
}

function markClampAppliedIfChanged(
  decision: ProtectEvaluation,
  originalMaxTokens: number | undefined,
  appliedMaxTokens: number | undefined,
): void {
  if (!decision.clamp || typeof appliedMaxTokens !== "number") {
    return;
  }
  if (typeof originalMaxTokens !== "number" || appliedMaxTokens < originalMaxTokens) {
    decision.clamp.applied = true;
  }
}

function extractResponseModel(response: unknown): string | null {
  if (response && typeof response === "object" && "model" in response) {
    const maybeModel = (response as { model?: unknown }).model;
    return typeof maybeModel === "string" ? maybeModel : null;
  }
  return null;
}

function extractTotalTokens(response: unknown): number | undefined {
  if (response && typeof response === "object" && "usage" in response) {
    const usage = (response as { usage?: { total_tokens?: unknown } }).usage;
    const totalTokens = usage?.total_tokens;
    if (typeof totalTokens === "number") {
      return totalTokens;
    }
  }
  return undefined;
}

function extractErrorType(error: unknown): string {
  if (error && typeof error === "object" && "name" in error) {
    const name = (error as { name?: unknown }).name;
    if (typeof name === "string" && name.length > 0) {
      return name;
    }
  }
  return "unknown";
}

function extractHttpStatus(error: unknown): number | undefined {
  if (!error || typeof error !== "object") {
    return undefined;
  }

  const withStatus = error as { status?: unknown; statusCode?: unknown; response?: { status?: unknown } };
  if (typeof withStatus.status === "number") {
    return withStatus.status;
  }
  if (typeof withStatus.statusCode === "number") {
    return withStatus.statusCode;
  }
  if (typeof withStatus.response?.status === "number") {
    return withStatus.response.status;
  }
  return undefined;
}
