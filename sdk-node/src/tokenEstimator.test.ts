import assert from "node:assert/strict";
import test from "node:test";

import { estimateInputTokensFromRequest } from "./tokenEstimator.js";

test("estimateInputTokensFromRequest counts full tool message payload", () => {
  const toolEstimate = estimateInputTokensFromRequest({
    model: "gpt-4o-mini",
    messages: [
      {
        role: "tool",
        tool_call_id: "call_123",
        content: "done",
      },
    ],
  });
  const textOnlyEstimate = estimateInputTokensFromRequest({
    model: "gpt-4o-mini",
    prompt: "done",
  });

  assert.equal(typeof toolEstimate, "number");
  assert.equal(typeof textOnlyEstimate, "number");
  assert.ok((toolEstimate ?? 0) > (textOnlyEstimate ?? 0));
});

test("estimateInputTokensFromRequest supports google contents payloads", () => {
  const contentsEstimate = estimateInputTokensFromRequest({
    model: "gemini-1.5-pro",
    contents: "hello from google",
  });

  assert.equal(typeof contentsEstimate, "number");
  assert.ok((contentsEstimate ?? 0) > 0);
});
