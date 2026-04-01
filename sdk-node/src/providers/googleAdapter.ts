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
  const targetGenerate = resolveGenerateTarget(googleModel);
  if (!targetGenerate) {
    return googleModel;
  }

  const originalGenerate = targetGenerate.fn.bind(targetGenerate.owner);
  targetGenerate.owner[targetGenerate.key] = async (
    ...args: unknown[]
  ) => {
    const traceId = generateTraceId();
    const spanId = generateSpanId();
    return bindTraceContext(traceId, spanId, async () => {
      const startedAt = Date.now();
      const requestedModel = extractRequestedModel(googleModel, args);
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
        requested_model: string | null;
        environment?: string;
        feature?: string;
        max_output_tokens?: number;
        input_tokens_estimate?: number;
        trace_id?: string;
        span_id?: string;
      } = {
        provider: "google",
        requested_model: requestedModel,
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
          requested_model: requestedModel,
          resolved_model: extractResponseModel(response),
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
          requested_model: requestedModel,
          resolved_model: null,
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
            error_message: extractErrorMessage(error),
            http_status: extractHttpStatus(error),
          },
        }));
        throw error;
      }
    });
  };

  return googleModel;
}

function resolveGenerateTarget(
  googleModel: Record<string, any>,
): { owner: Record<string, any>; fn: (...args: unknown[]) => Promise<unknown>; key: "generateContent" } | null {
  const directGenerate = googleModel?.generateContent;
  if (typeof directGenerate === "function") {
    return {
      owner: googleModel,
      fn: directGenerate as (...args: unknown[]) => Promise<unknown>,
      key: "generateContent",
    };
  }

  const models = googleModel?.models;
  const nestedGenerate = models?.generateContent;
  if (models && typeof nestedGenerate === "function") {
    return {
      owner: models as Record<string, any>,
      fn: nestedGenerate as (...args: unknown[]) => Promise<unknown>,
      key: "generateContent",
    };
  }

  return null;
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

function extractRequestedModel(googleModel: unknown, args: unknown[]): string | null {
  if (!googleModel || typeof googleModel !== "object") {
    const firstArg = args[0];
    if (firstArg && typeof firstArg === "object" && "model" in firstArg) {
      const payloadModel = (firstArg as { model?: unknown }).model;
      return typeof payloadModel === "string" ? payloadModel : null;
    }
    return null;
  }
  const withModel = googleModel as { model?: unknown; modelName?: unknown };
  if (typeof withModel.model === "string") {
    return withModel.model;
  }
  if (typeof withModel.modelName === "string") {
    return withModel.modelName;
  }
  const firstArg = args[0];
  if (firstArg && typeof firstArg === "object" && "model" in firstArg) {
    const payloadModel = (firstArg as { model?: unknown }).model;
    return typeof payloadModel === "string" ? payloadModel : null;
  }
  return null;
}

function extractMaxOutputTokens(args: unknown[]): number | undefined {
  const firstArg = args[0];
  if (!firstArg || typeof firstArg !== "object") {
    const secondArg = args[1];
    if (!secondArg || typeof secondArg !== "object") {
      return undefined;
    }
    const options = secondArg as {
      generationConfig?: { maxOutputTokens?: unknown };
      config?: { maxOutputTokens?: unknown };
    };
    const optionsGenerationMax = options.generationConfig?.maxOutputTokens;
    if (typeof optionsGenerationMax === "number") {
      return optionsGenerationMax;
    }
    const optionsConfigMax = options.config?.maxOutputTokens;
    return typeof optionsConfigMax === "number" ? optionsConfigMax : undefined;
  }
  const payload = firstArg as {
    generationConfig?: { maxOutputTokens?: unknown };
    config?: { maxOutputTokens?: unknown };
  };
  const generationMax = payload.generationConfig?.maxOutputTokens;
  if (typeof generationMax === "number") {
    return generationMax;
  }
  const configMax = payload.config?.maxOutputTokens;
  return typeof configMax === "number" ? configMax : undefined;
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

function extractResponseModel(response: unknown): string | null {
  if (!response || typeof response !== "object") {
    return null;
  }
  const topLevelModel = (response as { model?: unknown }).model;
  if (typeof topLevelModel === "string" && topLevelModel.trim()) {
    return topLevelModel;
  }
  const nestedResponse = (response as { response?: { modelVersion?: unknown; model?: unknown } }).response;
  if (typeof nestedResponse?.modelVersion === "string" && nestedResponse.modelVersion.trim()) {
    return nestedResponse.modelVersion;
  }
  if (typeof nestedResponse?.model === "string" && nestedResponse.model.trim()) {
    return nestedResponse.model;
  }
  return null;
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

function extractErrorMessage(error: unknown): string | undefined {
  if (error && typeof error === "object" && "message" in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string" && message.length > 0) {
      return message;
    }
  }
  return undefined;
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
    const useModernConfig = "config" in payload || "contents" in payload || "model" in payload;
    const configKey = useModernConfig ? "config" : "generationConfig";
    const existingConfig =
      payload[configKey] && typeof payload[configKey] === "object"
        ? (payload[configKey] as Record<string, unknown>)
        : {};
    const existingMax = existingConfig.maxOutputTokens;
    payload[configKey] = {
      ...existingConfig,
      maxOutputTokens: typeof existingMax === "number" ? Math.min(existingMax, recommended) : recommended,
    };
    nextArgs[0] = payload;
    return nextArgs;
  }

  const secondArg = nextArgs[1];
  const existingOptions =
    secondArg && typeof secondArg === "object" ? ({ ...(secondArg as Record<string, unknown>) } as Record<string, unknown>) : {};
  const configKey =
    existingOptions.config && typeof existingOptions.config === "object" ? "config" : "generationConfig";
  const generationConfig =
    existingOptions[configKey] && typeof existingOptions[configKey] === "object"
      ? ({ ...(existingOptions[configKey] as Record<string, unknown>) } as Record<string, unknown>)
      : {};
  const existingMax = generationConfig.maxOutputTokens;
  generationConfig.maxOutputTokens = typeof existingMax === "number" ? Math.min(existingMax, recommended) : recommended;
  existingOptions[configKey] = generationConfig;
  nextArgs[1] = existingOptions;
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
