export const sdkNodeConfig = {
  defaultBaseUrl: "http://localhost:8000",
  defaultEnvironment: "dev",
  defaultFlushIntervalMs: 1000,
  defaultMaxQueueSize: 1000,
  defaultFlushTimeoutMs: 500,
  defaultRequestTimeoutMs: 1000,
  retryDelayMinMs: 200,
  retryDelayMaxMs: 400,
} as const;
