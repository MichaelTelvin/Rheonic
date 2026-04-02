import { encoding_for_model, get_encoding, type Tiktoken } from "@dqbd/tiktoken";

import { sdkNodeConfig } from "./config.js";

const encoderCache = new Map<string, Tiktoken>();

export function prewarmTokenEstimator(model: string | null = null): void {
  try {
    getEncoder(model);
  } catch {
    return;
  }
}

export function estimateInputTokensFromRequest(payload: unknown): number | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const request = payload as { model?: unknown; messages?: unknown; prompt?: unknown };
  const text = extractTextForEstimation(request);
  if (text === null) {
    return null;
  }
  try {
    const encoder = getEncoder(typeof request.model === "string" ? request.model : null);
    const encodedLength = encoder.encode(text).length;
    return Math.min(sdkNodeConfig.maxInputTokenEstimate, encodedLength);
  } catch {
    return null;
  }
}

function extractTextForEstimation(request: { messages?: unknown; prompt?: unknown; contents?: unknown }): string | null {
  if (Array.isArray(request.messages)) {
    try {
      return JSON.stringify(request.messages);
    } catch {
      return null;
    }
  }

  if (typeof request.prompt === "string") {
    return request.prompt;
  }

  if (typeof request.contents === "string") {
    return request.contents;
  }

  if (Array.isArray(request.contents)) {
    try {
      return JSON.stringify(request.contents);
    } catch {
      return null;
    }
  }

  return null;
}

function getEncoder(model: string | null): Tiktoken {
  const cacheKey = model ?? sdkNodeConfig.defaultTokenizerEncoding;
  const cached = encoderCache.get(cacheKey);
  if (cached) {
    return cached;
  }

  let encoder: Tiktoken;
  if (model) {
    try {
      encoder = encoding_for_model(model as Parameters<typeof encoding_for_model>[0]);
    } catch {
      encoder = get_encoding(sdkNodeConfig.defaultTokenizerEncoding);
    }
  } else {
    encoder = get_encoding(sdkNodeConfig.defaultTokenizerEncoding);
  }

  encoderCache.set(cacheKey, encoder);
  return encoder;
}
