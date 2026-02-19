import { encoding_for_model, get_encoding, type Tiktoken } from "@dqbd/tiktoken";

const encoderCache = new Map<string, Tiktoken>();
const DEFAULT_ENCODING = "cl100k_base";

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
    return encoder.encode(text).length;
  } catch {
    return null;
  }
}

function extractTextForEstimation(request: { messages?: unknown; prompt?: unknown }): string | null {
  if (Array.isArray(request.messages)) {
    const parts: string[] = [];
    for (const message of request.messages) {
      if (!message || typeof message !== "object") {
        return null;
      }
      const content = (message as { content?: unknown }).content;
      if (typeof content === "string") {
        parts.push(content);
        continue;
      }
      if (Array.isArray(content)) {
        for (const item of content) {
          if (!item || typeof item !== "object") {
            return null;
          }
          const text = (item as { text?: unknown }).text;
          if (typeof text === "string") {
            parts.push(text);
          }
        }
        continue;
      }
      return null;
    }
    return parts.join("\n");
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
