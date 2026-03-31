import { buildEvent } from "../eventBuilder.js";
import { bindTraceContext, generateSpanId, generateTraceId } from "../logger.js";
import { RHEONICBlockedError, type ProtectEvaluation } from "../protectEngine.js";
import { validateProviderModel } from "../providerModelValidation.js";
import { estimateInputTokensFromRequest } from "../tokenEstimator.js";

import type { Client } from "../client.js";

export interface GoogleInstrumentationOptions {
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

export function instrumentGoogle<T extends Record<string, any>>(googleModel: T, options: GoogleInstrumentationOptions): T {
  const targetGenerate = googleModel?.generateContent;
  if (typeof targetGenerate !== "function") {
    return googleModel;
  }

  const originalGenerate = targetGenerate.bind(googleModel);
  (googleModel as unknown as { generateContent: (...args: unknown[]) => Promise<unknown> }).generateContent = async (
    ...args: unknown[]
  ) => {
    const traceId = generateTraceId();
    const spanId = generateSpanId();
    return bindTraceContext(traceId, spanId, async () => {
      const startedAt = Date.now();
      const requestedModel = extractRequestedModel(googleModel);
      validateProviderModel("google", requestedModel);
      const requestPayload = extractRequestPayload(args, requestedModel);
      let estimatedInputTokens: number | null = null;

      const tokenEstimateStartedAt = Date.now();
      estimatedInputTokens = requestPayload
        ? (estimatorOverrideForTests
            ? estimatorOverrideForTests(requestPayload)
            : estimateInputTokensFromRequest(requestPayload))
        : null;
      options.client.debugLog("Protect token estimation completed", {
        provider: "google",
        model: requestedModel,
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
        trace_id?: string;
        span_id?: string;
      } = {
        provider: "google",
        model: requestedModel,
        environment: options.environment ?? options.client.environment,
        feature: options.feature,
        max_output_tokens: extractMaxOutputTokens(args),
        trace_id: traceId,
        span_id: spanId,
      };
      if (typeof estimatedInputTokens === "number") {
        protectPayload.input_tokens_estimate = estimatedInputTokens;
      }
      const protectDecision = await options.client.evaluateProtectDecision(protectPayload);

      if (protectDecision.decision === "block") {
        throw new RHEONICBlockedError(protectDecision);
      }
      const callArgs = maybeApplyGoogleClamp(args, protectDecision);
      markClampAppliedIfChanged(protectDecision, extractMaxOutputTokens(args), extractMaxOutputTokens(callArgs));

      try {
        const response = await originalGenerate(...callArgs);
        await options.client.captureEventAndFlush(buildEvent({
          provider: "google",
          model: requestedModel,
          environment: options.environment ?? options.client.environment,
          request: {
            endpoint: options.endpoint,
            feature: options.feature,
            token_explosion_tokens: typeof estimatedInputTokens === "number" ? estimatedInputTokens : undefined,
            input_tokens_estimate: typeof estimatedInputTokens === "number" ? estimatedInputTokens : undefined,
            protect_decision: protectDecision.decision !== "allow" ? protectDecision.decision : undefined,
            protect_reason: protectDecision.decision !== "allow" ? protectDecision.reason : undefined,
          },
          response: {
            latency_ms: Date.now() - startedAt,
            total_tokens: extractTotalTokens(response),
            http_status: 200,
          },
        }));
        return response;
      } catch (error) {
        await options.client.captureEventAndFlush(buildEvent({
          provider: "google",
          model: requestedModel,
          environment: options.environment ?? options.client.environment,
          request: {
            endpoint: options.endpoint,
            feature: options.feature,
            token_explosion_tokens: typeof estimatedInputTokens === "number" ? estimatedInputTokens : undefined,
            input_tokens_estimate: typeof estimatedInputTokens === "number" ? estimatedInputTokens : undefined,
            protect_decision: protectDecision.decision !== "allow" ? protectDecision.decision : undefined,
            protect_reason: protectDecision.decision !== "allow" ? protectDecision.reason : undefined,
          },
          response: {
            latency_ms: Date.now() - startedAt,
            error_type: extractErrorType(error),
            http_status: extractHttpStatus(error),
          },
        }));
        throw error;
      }
    });
  };

  return googleModel;
}

function extractRequestPayload(args: unknown[], model: string | null): Record<string, unknown> | null {
  const firstArg = args[0];
  if (typeof firstArg === "string") {
    return { model, prompt: firstArg };
  }
  if (firstArg && typeof firstArg === "object") {
    return firstArg as Record<string, unknown>;
  }
  return null;
}

function extractRequestedModel(googleModel: unknown): string | null {
  if (!googleModel || typeof googleModel !== "object") {
    return null;
  }
  const withModel = googleModel as { model?: unknown; modelName?: unknown };
  if (typeof withModel.model === "string") {
    return withModel.model;
  }
  if (typeof withModel.modelName === "string") {
    return withModel.modelName;
  }
  return null;
}

function extractMaxOutputTokens(args: unknown[]): number | undefined {
  const firstArg = args[0];
  if (!firstArg || typeof firstArg !== "object") {
    return undefined;
  }
  const payload = firstArg as { generationConfig?: { maxOutputTokens?: unknown } };
  const maxOutput = payload.generationConfig?.maxOutputTokens;
  return typeof maxOutput === "number" ? maxOutput : undefined;
}

function extractTotalTokens(response: unknown): number | undefined {
  if (!response || typeof response !== "object") {
    return undefined;
  }
  const usageMetadata = (response as { response?: { usageMetadata?: unknown }; usageMetadata?: unknown }).response?.usageMetadata
    ?? (response as { usageMetadata?: unknown }).usageMetadata;
  if (!usageMetadata || typeof usageMetadata !== "object") {
    return undefined;
  }
  const usage = usageMetadata as {
    totalTokenCount?: unknown;
    promptTokenCount?: unknown;
    candidatesTokenCount?: unknown;
  };
  if (typeof usage.totalTokenCount === "number") {
    return usage.totalTokenCount;
  }
  const prompt = typeof usage.promptTokenCount === "number" ? usage.promptTokenCount : 0;
  const candidates = typeof usage.candidatesTokenCount === "number" ? usage.candidatesTokenCount : 0;
  const total = prompt + candidates;
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


function maybeApplyGoogleClamp(args: unknown[], decision: ProtectEvaluation): unknown[] {
  if (decision.decision !== "clamp") {
    return args;
  }
  if (!decision.applyClampEnabled) {
    return args;
  }
  const recommended = decision.clamp?.recommended_max_output_tokens;
  if (typeof recommended !== "number" || recommended < 1) {
    return args;
  }
  const nextArgs = [...args];
  const firstArg = nextArgs[0];
  if (firstArg && typeof firstArg === "object") {
    const payload = { ...(firstArg as Record<string, unknown>) };
    const existingConfig =
      payload.generationConfig && typeof payload.generationConfig === "object"
        ? (payload.generationConfig as Record<string, unknown>)
        : {};
    const existingMax = existingConfig.maxOutputTokens;
    payload.generationConfig = {
      ...existingConfig,
      maxOutputTokens: typeof existingMax === "number" ? Math.min(existingMax, recommended) : recommended,
    };
    nextArgs[0] = payload;
    return nextArgs;
  }

  const secondArg = nextArgs[1];
  const existingConfig =
    secondArg && typeof secondArg === "object" ? ({ ...(secondArg as Record<string, unknown>) } as Record<string, unknown>) : {};
  const generationConfig =
    existingConfig.generationConfig && typeof existingConfig.generationConfig === "object"
      ? ({ ...(existingConfig.generationConfig as Record<string, unknown>) } as Record<string, unknown>)
      : {};
  const existingMax = generationConfig.maxOutputTokens;
  generationConfig.maxOutputTokens = typeof existingMax === "number" ? Math.min(existingMax, recommended) : recommended;
  existingConfig.generationConfig = generationConfig;
  nextArgs[1] = existingConfig;
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
