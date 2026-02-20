import { encoding_for_model, get_encoding, type Tiktoken } from "@dqbd/tiktoken";

const encoderCache = new Map<string, Tiktoken>();
const DEFAULT_ENCODING = "cl100k_base";
const MAX_INPUT_TOKEN_ESTIMATE = 50_000;

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
    return Math.min(MAX_INPUT_TOKEN_ESTIMATE, encodedLength);
  } catch {
    return null;
  }
}

function extractTextForEstimation(request: { messages?: unknown; prompt?: unknown }): string | null {
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

  return null;
}

function getEncoder(model: string | null): Tiktoken {
  const cacheKey = model ?? DEFAULT_ENCODING;
  const cached = encoderCache.get(cacheKey);
  if (cached) {
    return cached;
  }

  let encoder: Tiktoken;
  if (model) {
    try {
      encoder = encoding_for_model(model as Parameters<typeof encoding_for_model>[0]);
    } catch {
      encoder = get_encoding(DEFAULT_ENCODING);
    }
  } else {
    encoder = get_encoding(DEFAULT_ENCODING);
  }

  encoderCache.set(cacheKey, encoder);
  return encoder;
}
