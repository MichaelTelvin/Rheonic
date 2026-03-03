import type { Client } from "../client.js";
import { buildEvent } from "../eventBuilder.js";
import { validateProviderModel } from "../providerModelValidation.js";
import { RHEONICBlockedError, type ProtectEvaluation } from "../protectEngine.js";
import { estimateInputTokensFromRequest } from "../tokenEstimator.js";

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
    const startedAt = Date.now();
    const requestedModel = extractRequestedModel(googleModel);
    validateProviderModel("google", requestedModel);
    const requestPayload = extractRequestPayload(args, requestedModel);
    let estimatedInputTokens: number | null = null;

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
      provider: "google",
      model: requestedModel,
      environment: options.environment ?? options.client.environment,
      feature: options.feature,
      max_output_tokens: extractMaxOutputTokens(args),
    };
    if (typeof estimatedInputTokens === "number") {
      protectPayload.input_tokens_estimate = estimatedInputTokens;
    }
    const protectDecision = await options.client.evaluateProtectDecision(protectPayload);

    if (protectDecision.decision === "block") {
      throw new RHEONICBlockedError(protectDecision.reason);
    }
    const callArgs = maybeApplyGoogleClamp(args, protectDecision);

    try {
      const response = await originalGenerate(...callArgs);
      void options.client.captureEvent(
        buildEvent({
          provider: "google",
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
            total_tokens: extractTotalTokens(response),
            http_status: 200,
          },
        }),
      );
      return response;
    } catch (error) {
      void options.client.captureEvent(
        buildEvent({
          provider: "google",
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
