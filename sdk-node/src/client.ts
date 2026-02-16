import type { EventPayload } from "./eventBuilder.js";

const DEFAULT_BASE_URL = "http://localhost:8000";
const DEFAULT_ENVIRONMENT = "dev";
const DEFAULT_FLUSH_INTERVAL_MS = 1000;
const DEFAULT_MAX_QUEUE_SIZE = 1000;
const DEFAULT_FLUSH_TIMEOUT_MS = 500;

const CLIENT_REGISTRY = new Set<Client>();
let EXIT_HOOKS_REGISTERED = false;

export interface ClientConfig {
  baseUrl?: string;
  ingestKey: string;
  environment?: string;
  flushIntervalMs?: number;
  maxQueueSize?: number;
}

export class Client {
  public readonly baseUrl: string;
  public readonly ingestKey: string;
  public readonly environment: string;

  private readonly flushIntervalMs: number;
  private readonly maxQueueSize: number;
  private queue: EventPayload[] = [];
  private isFlushing = false;
  private timer: ReturnType<typeof setInterval> | null = null;

  public constructor(config: ClientConfig) {
    this.baseUrl = config.baseUrl ?? DEFAULT_BASE_URL;
    this.ingestKey = config.ingestKey;
    this.environment = config.environment ?? DEFAULT_ENVIRONMENT;
    this.flushIntervalMs = config.flushIntervalMs ?? DEFAULT_FLUSH_INTERVAL_MS;
    this.maxQueueSize = config.maxQueueSize ?? DEFAULT_MAX_QUEUE_SIZE;

    this.timer = setInterval(() => {
      void this.flush();
    }, this.flushIntervalMs);
    this.timer.unref?.();

    CLIENT_REGISTRY.add(this);
    registerExitHooks();
  }

  public async captureEvent(event: EventPayload): Promise<void> {
    try {
      if (this.queue.length >= this.maxQueueSize) {
        return;
      }

      this.queue.push({
        ...event,
        environment: event.environment || this.environment,
      });
    } catch {
      return;
    }
  }

  public async flush(): Promise<void> {
    if (this.isFlushing) {
      return;
    }

    this.isFlushing = true;
    try {
      while (this.queue.length > 0) {
        const event = this.queue.shift();
        if (!event) {
          continue;
        }
        await this.sendEvent(event);
      }
    } finally {
      this.isFlushing = false;
    }
  }

  public async flushWithTimeout(timeoutMs = DEFAULT_FLUSH_TIMEOUT_MS): Promise<void> {
    await Promise.race([
      this.flush(),
      new Promise<void>((resolve) => {
        setTimeout(resolve, timeoutMs);
      }),
    ]);
  }

  public close(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    CLIENT_REGISTRY.delete(this);
  }

  private async sendEvent(event: EventPayload): Promise<void> {
    const fetchFn = await resolveFetch();
    if (!fetchFn) {
      return;
    }

    try {
      await fetchFn(`${this.baseUrl}/api/v1/events`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Project-Ingest-Key": this.ingestKey,
        },
        body: JSON.stringify(event),
      });
    } catch {
      return;
    }
  }
}

async function resolveFetch(): Promise<typeof fetch | null> {
  if (typeof globalThis.fetch === "function") {
    return globalThis.fetch.bind(globalThis);
  }

  try {
    const undici = (await import("undici" as string)) as { fetch: typeof fetch };
    return undici.fetch as typeof fetch;
  } catch {
    return null;
  }
}

function registerExitHooks(): void {
  if (EXIT_HOOKS_REGISTERED || typeof process === "undefined") {
    return;
  }

  EXIT_HOOKS_REGISTERED = true;

  process.on("beforeExit", () => {
    void flushAllClients();
  });

  process.on("SIGINT", () => {
    void flushAllClients().finally(() => {
      process.exit(0);
    });
  });

  process.on("SIGTERM", () => {
    void flushAllClients().finally(() => {
      process.exit(0);
    });
  });
}

async function flushAllClients(): Promise<void> {
  await Promise.all(Array.from(CLIENT_REGISTRY, (client) => client.flushWithTimeout()));
}
