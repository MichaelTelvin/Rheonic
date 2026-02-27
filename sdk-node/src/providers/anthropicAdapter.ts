import type { Client } from "../client.js";
import { buildEvent } from "../eventBuilder.js";
import { validateProviderModel } from "../providerModelValidation.js";
import { LLMTBGBlockedError, type ProtectEvaluation } from "../protectEngine.js";
import { estimateInputTokensFromRequest } from "../tokenEstimator.js";

export interface AnthropicInstrumentationOptions {
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

export function instrumentAnthropic<T extends Record<string, any>>(
  anthropicClient: T,
  options: AnthropicInstrumentationOptions,
): T {
  const targetCreate = anthropicClient?.messages?.create;
  if (typeof targetCreate !== "function") {
    return anthropicClient;
  }

  const originalCreate = targetCreate.bind(anthropicClient.messages);
  anthropicClient.messages.create = async (...args: unknown[]) => {
    const startedAt = Date.now();
    const requestPayload = extractRequestPayload(args);
    const requestedModel = extractRequestedModel(args);
    validateProviderModel("anthropic", requestedModel);
    let estimatedInputTokens: number | null = null;

    let protectDecision = { decision: "allow", reason: "protect_disabled" } as ProtectEvaluation;
    if (options.client.shouldPreflightDecision()) {
      estimatedInputTokens = requestPayload
        ? (estimatorOverrideForTests
            ? estimatorOverrideForTests(requestPayload)
            : estimateInputTokensFromRequest(requestPayload))
        : null;
      const protectPayload: {
        provider: string;
        model: string | null;
        environment?: string;
        feature?: string;
        max_output_tokens?: number;
        input_tokens_estimate?: number;
      } = {
        provider: "anthropic",
        model: requestedModel,
        environment: options.environment ?? options.client.environment,
        feature: options.feature,
        max_output_tokens: extractMaxOutputTokens(args),
      };
      if (typeof estimatedInputTokens === "number") {
        protectPayload.input_tokens_estimate = estimatedInputTokens;
      }
      protectDecision = await options.client.evaluateProtectDecision(protectPayload);
    }

    if (protectDecision.decision === "block") {
      throw new LLMTBGBlockedError(protectDecision.reason);
    }
    const callArgs = maybeApplyAnthropicClamp(args, protectDecision);

    try {
      const response = await originalCreate(...callArgs);
      void options.client.captureEvent(
        buildEvent({
          provider: "anthropic",
          model: extractResponseModel(response) ?? requestedModel,
          environment: options.environment ?? options.client.environment,
          request: {
            endpoint: options.endpoint,
            feature: options.feature,
            input_tokens_estimate: typeof estimatedInputTokens === "number" ? estimatedInputTokens : undefined,
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
          provider: "anthropic",
          model: requestedModel,
          environment: options.environment ?? options.client.environment,
          request: {
            endpoint: options.endpoint,
            feature: options.feature,
            input_tokens_estimate: typeof estimatedInputTokens === "number" ? estimatedInputTokens : undefined,
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

  return anthropicClient;
}

function extractRequestPayload(args: unknown[]): Record<string, unknown> | null {
  const firstArg = args[0];
  if (!firstArg || typeof firstArg !== "object") {
    return null;
  }
  return firstArg as Record<string, unknown>;
}

function extractRequestedModel(args: unknown[]): string | null {
  const payload = extractRequestPayload(args);
  const model = payload?.model;
  return typeof model === "string" ? model : null;
}

function extractMaxOutputTokens(args: unknown[]): number | undefined {
  const payload = extractRequestPayload(args);
  const maxTokens = payload?.max_tokens;
  return typeof maxTokens === "number" ? maxTokens : undefined;
}

function extractResponseModel(response: unknown): string | null {
  if (response && typeof response === "object" && "model" in response) {
    const model = (response as { model?: unknown }).model;
    return typeof model === "string" ? model : null;
  }
  return null;
}

function extractTotalTokens(response: unknown): number | undefined {
  if (!response || typeof response !== "object") {
    return undefined;
  }
  const usage = (response as { usage?: { total_tokens?: unknown; input_tokens?: unknown; output_tokens?: unknown } }).usage;
  if (typeof usage?.total_tokens === "number") {
    return usage.total_tokens;
  }
  const input = typeof usage?.input_tokens === "number" ? usage.input_tokens : 0;
  const output = typeof usage?.output_tokens === "number" ? usage.output_tokens : 0;
  const total = input + output;
  return total > 0 ? total : undefined;
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

function maybeApplyAnthropicClamp(args: unknown[], decision: ProtectEvaluation): unknown[] {
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
  const maxTokens = payload.max_tokens;
  if (typeof maxTokens === "number") {
    payload.max_tokens = Math.min(maxTokens, recommended);
  } else {
    payload.max_tokens = recommended;
  }
  const nextArgs = [...args];
  nextArgs[0] = payload;
  return nextArgs;
}
