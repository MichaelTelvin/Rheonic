import { Client, type ClientConfig, type ClientStats, type OverflowPolicy } from "./client.js";
import { buildEvent, type BuildEventInput, type EventPayload } from "./eventBuilder.js";
import { LLMTBGBlockedError } from "./protectEngine.js";
import { instrumentOpenAI as instrumentOpenAIProvider, type OpenAIInstrumentationOptions } from "./providers/openaiAdapter.js";

let defaultClient: Client | null = null;

export {
  Client,
  LLMTBGBlockedError,
  type ClientConfig,
  type ClientStats,
  type OverflowPolicy,
  buildEvent,
  type BuildEventInput,
  type EventPayload,
};

export function createClient(config: ClientConfig): Client {
  if (defaultClient) {
    defaultClient.close();
  }
  const client = new Client(config);
  defaultClient = client;
  return client;
}

export async function captureEvent(event: EventPayload | BuildEventInput): Promise<void> {
  if (!defaultClient) {
    return;
  }

  const payload = "provider" in event && "ts" in event ? (event as EventPayload) : buildEvent(event as BuildEventInput);
  await defaultClient.captureEvent(payload);
}

export function instrumentOpenAI<T extends Record<string, any>>(
  openaiClient: T,
  options?: Omit<OpenAIInstrumentationOptions, "client"> & { client?: Client },
): T {
  const resolvedClient = options?.client ?? defaultClient;
  if (!resolvedClient) {
    return openaiClient;
  }

  return instrumentOpenAIProvider(openaiClient, {
    client: resolvedClient,
    environment: options?.environment,
    endpoint: options?.endpoint,
    feature: options?.feature,
  });
}
