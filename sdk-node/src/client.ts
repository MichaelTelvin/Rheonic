import { sdkNodeConfig } from "./config.js";
import { requestJson } from "./httpTransport.js";
import { bindTraceContext, emitLog, generateSpanId, generateTraceId, getSpanId, getTraceId } from "./logger.js";
import { ProtectEngine, type ProtectContext, type ProtectEvaluation, type ProtectFailMode } from "./protectEngine.js";
import { instrumentAnthropic as instrumentAnthropicProvider, type AnthropicInstrumentationOptions } from "./providers/anthropicAdapter.js";
import { instrumentGoogle as instrumentGoogleProvider, type GoogleInstrumentationOptions } from "./providers/googleAdapter.js";
import { instrumentOpenAI as instrumentOpenAIProvider, type OpenAIInstrumentationOptions } from "./providers/openaiAdapter.js";
import { prewarmTokenEstimator } from "./tokenEstimator.js";

import type { EventPayload } from "./eventBuilder.js";

export type OverflowPolicy = "drop_oldest" | "drop_newest";

export interface ClientStats {
  queued: number;
  dropped: number;
  sent: number;
  failed: number;
}

const CLIENT_REGISTRY = new Set<Client>();
let EXIT_HOOKS_REGISTERED = false;

export interface ClientConfig {
  baseUrl?: string;
  ingestKey: string;
  environment?: string;
  flushIntervalMs?: number;
  maxQueueSize?: number;
  overflowPolicy?: OverflowPolicy;
  requestTimeoutMs?: number;
  protectFailMode?: ProtectFailMode;
  debug?: boolean;
}

export class Client {
  public readonly baseUrl: string;
  public readonly ingestKey: string;
  public readonly environment: string;

  private readonly flushIntervalMs: number;
  private readonly maxQueueSize: number;
  private readonly overflowPolicy: OverflowPolicy;
  private readonly requestTimeoutMs: number;
  private readonly protectEngine: ProtectEngine;
  private readonly debug: boolean;
  private queue: EventPayload[] = [];
  private isFlushing = false;
  private timer: ReturnType<typeof setInterval> | null = null;
  private dropped = 0;
  private sent = 0;
  private failed = 0;
  private isClosed = false;
  private warmupPromise: Promise<void> | null = null;
  private warmupCompleted = false;

  public constructor(config: ClientConfig) {
    this.baseUrl = config.baseUrl ?? process.env.RHEONIC_BASE_URL ?? sdkNodeConfig.defaultBaseUrl;
    this.ingestKey = config.ingestKey;
    this.environment =
      config.environment ??
      process.env.NODE_ENV ??
      process.env.APP_ENV ??
      process.env.ENVIRONMENT ??
      process.env.ENV ??
      sdkNodeConfig.defaultEnvironment;
    this.flushIntervalMs = config.flushIntervalMs ?? sdkNodeConfig.defaultFlushIntervalMs;
    this.maxQueueSize = config.maxQueueSize ?? sdkNodeConfig.defaultMaxQueueSize;
    this.overflowPolicy = config.overflowPolicy ?? "drop_oldest";
    this.requestTimeoutMs = config.requestTimeoutMs ?? sdkNodeConfig.defaultRequestTimeoutMs;
    const initialFailMode = config.protectFailMode ?? sdkNodeConfig.defaultProtectFailMode;
    const envDebug = process.env.RHEONIC_DEBUG === "1" || process.env.RHEONIC_DEBUG === "true";
    this.debug = config.debug ?? envDebug;

    // Warm default/model-specific tokenizer state before the first protected call.
    prewarmTokenEstimator(null);
    const prewarmModel = process.env.RHEONIC_MODEL?.trim();
    if (prewarmModel) {
      prewarmTokenEstimator(prewarmModel);
    }

    this.protectEngine = new ProtectEngine({
      baseUrl: this.baseUrl,
      ingestKey: this.ingestKey,
      environment: this.environment,
      fallbackRequestTimeoutMs: this.requestTimeoutMs,
      initialFailMode,
      debugLog: this.debugLog.bind(this),
    });
    this.warmupPromise = this.runWarmup();

    this.timer = setInterval(() => {
      void this.flush();
    }, this.flushIntervalMs);
    this.timer.unref?.();

    CLIENT_REGISTRY.add(this);
    registerExitHooks();
    emitLog({
      level: "info",
      event: "sdk_client_initialized",
      message: "SDK client initialized",
      environment: this.environment,
      traceId: generateTraceId(),
      spanId: generateSpanId(),
    });
  }

  public async captureEvent(event: EventPayload): Promise<void> {
    try {
      if (this.queue.length >= this.maxQueueSize) {
        if (this.overflowPolicy === "drop_oldest") {
          this.queue.shift();
          this.dropped += 1;
        } else {
          this.dropped += 1;
          return;
        }
      }

      if (this.isClosed) {
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

  public getStats(): ClientStats {
    return {
      queued: this.queue.length,
      dropped: this.dropped,
      sent: this.sent,
      failed: this.failed,
    };
  }

  public async flush(): Promise<void> {
    if (this.isFlushing || this.isClosed) {
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

  public async evaluateProtectDecision(context: ProtectContext): Promise<ProtectEvaluation> {
    await this.ensureWarmup();
    return this.protectEngine.evaluate(context);
  }

  public async warmConnections(): Promise<void> {
    if (this.warmupCompleted) {
      return;
    }
    if (this.warmupPromise) {
      await this.warmupPromise;
      this.warmupPromise = null;
      return;
    }
    this.warmupPromise = this.runWarmup();
    await this.warmupPromise;
    this.warmupPromise = null;
  }

  private async ensureWarmup(): Promise<void> {
    if (this.warmupCompleted) {
      return;
    }
    if (this.warmupPromise) {
      await this.warmupPromise;
      this.warmupPromise = null;
    }
  }

  private async runWarmup(): Promise<void> {
    try {
      const response = await bindTraceContext(generateTraceId(), generateSpanId(), async () => await requestJson(`${this.baseUrl}/health`, {
        method: "GET",
        headers: {
          "X-Trace-ID": getTraceId(),
          "X-Span-ID": getSpanId(),
        },
      }));
      this.debugLog("SDK connection warmup completed", { status_code: response.status });
    } catch {
      this.debugLog("SDK connection warmup failed");
    }
    try {
      await this.protectEngine.bootstrap();
      this.debugLog("SDK protect config bootstrap completed");
    } catch {
      this.debugLog("SDK protect config bootstrap failed");
    }
    this.warmupCompleted = true;
  }

  public instrumentOpenAI<T extends Record<string, any>>(
    openaiClient: T,
    options?: Omit<OpenAIInstrumentationOptions, "client">,
  ): T {
    return instrumentOpenAIProvider(openaiClient, {
      client: this,
      environment: options?.environment,
      endpoint: options?.endpoint,
      feature: options?.feature,
    });
  }

  public instrumentAnthropic<T extends Record<string, any>>(
    anthropicClient: T,
    options?: Omit<AnthropicInstrumentationOptions, "client">,
  ): T {
    return instrumentAnthropicProvider(anthropicClient, {
      client: this,
      environment: options?.environment,
      endpoint: options?.endpoint,
      feature: options?.feature,
    });
  }

  public instrumentGoogle<T extends Record<string, any>>(
    googleModel: T,
    options?: Omit<GoogleInstrumentationOptions, "client">,
  ): T {
    return instrumentGoogleProvider(googleModel, {
      client: this,
      environment: options?.environment,
      endpoint: options?.endpoint,
      feature: options?.feature,
    });
  }

  public async flushWithTimeout(timeoutMs = sdkNodeConfig.defaultFlushTimeoutMs): Promise<void> {
    await Promise.race([
      this.flush(),
      new Promise<void>((resolve) => {
        setTimeout(resolve, timeoutMs);
      }),
    ]);
  }

  public close(): void {
    if (this.isClosed) {
      return;
    }
    this.isClosed = true;
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    CLIENT_REGISTRY.delete(this);
  }

  private async sendEvent(event: EventPayload): Promise<void> {
    const firstAttempt = await this.sendEventOnce(event);
    if (firstAttempt.ok) {
      this.sent += 1;
      return;
    }

    if (!firstAttempt.shouldRetry) {
      this.failed += 1;
      return;
    }

    await waitMs(jitterMs(sdkNodeConfig.retryDelayMinMs, sdkNodeConfig.retryDelayMaxMs));
    const secondAttempt = await this.sendEventOnce(event);
    if (secondAttempt.ok) {
      this.sent += 1;
      return;
    }

    this.failed += 1;
  }

  private async sendEventOnce(event: EventPayload): Promise<{ ok: boolean; shouldRetry: boolean }> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.requestTimeoutMs);
    const traceId = generateTraceId();
    const spanId = generateSpanId();
    try {
      const response = await bindTraceContext(traceId, spanId, async () => await requestJson(`${this.baseUrl}/api/v1/events`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Project-Ingest-Key": this.ingestKey,
          "X-Trace-ID": getTraceId(),
          "X-Span-ID": spanId,
        },
        body: JSON.stringify(event),
        signal: controller.signal,
      }));
      clearTimeout(timeout);
      if (response.ok) {
        return { ok: true, shouldRetry: false };
      }
      if (response.status >= 500) {
        this.debugLog(`Server error ${response.status}; scheduling retry`);
        return { ok: false, shouldRetry: true };
      }
      return { ok: false, shouldRetry: false };
    } catch {
      clearTimeout(timeout);
      return { ok: false, shouldRetry: true };
    }
  }

  public debugLog(message: string, meta?: Record<string, unknown>): void {
    if (!this.debug) {
      return;
    }
    emitLog({
      level: "debug",
      event: "sdk_debug",
      message,
      metadata: meta,
      environment: this.environment,
    });
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

function jitterMs(minMs: number, maxMs: number): number {
  return Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs;
}

function waitMs(delayMs: number): Promise<void> {
  return new Promise<void>((resolve) => {
    setTimeout(resolve, delayMs);
  });
}
