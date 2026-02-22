export const sdkNodeConfig = {
  defaultBaseUrl: "http://localhost:8000",
  defaultEnvironment: "dev",
  defaultFlushIntervalMs: 1000,
  defaultMaxQueueSize: 1000,
  defaultFlushTimeoutMs: 500,
  defaultRequestTimeoutMs: 1000,
  defaultProtectDecisionTimeoutMs: 100,
  defaultProtectFailMode: "open",
  retryDelayMinMs: 200,
  retryDelayMaxMs: 400,
  defaultTokenizerEncoding: "cl100k_base",
  maxInputTokenEstimate: 50_000,
} as const;
