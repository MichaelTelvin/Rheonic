import http from "node:http";
import https from "node:https";

const HTTP_AGENT = new http.Agent({
  keepAlive: true,
  maxSockets: 32,
});

const HTTPS_AGENT = new https.Agent({
  keepAlive: true,
  maxSockets: 32,
});

type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export interface JsonRequestOptions {
  method: "GET" | "POST";
  headers?: Record<string, string>;
  body?: string;
  signal?: AbortSignal;
}

export interface JsonHttpResponse {
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
}

class BufferedJsonResponse implements JsonHttpResponse {
  public readonly ok: boolean;

  public constructor(
    public readonly status: number,
    private readonly payload: string,
  ) {
    this.ok = status >= 200 && status < 300;
  }

  public async json(): Promise<unknown> {
    if (!this.payload) {
      return {};
    }
    return JSON.parse(this.payload) as JsonValue;
  }
}

export async function requestJson(url: string, options: JsonRequestOptions): Promise<JsonHttpResponse> {
  if (typeof globalThis.fetch === "function") {
    const response = await globalThis.fetch(url, {
      method: options.method,
      headers: options.headers,
      body: options.body,
      signal: options.signal,
    });
    const textReader = (response as Response & { text?: () => Promise<string> }).text;
    const payload =
      typeof textReader === "function"
        ? await textReader.call(response)
        : await serializeFetchJson(response as Response & { json?: () => Promise<unknown> });
    return new BufferedJsonResponse(response.status, payload);
  }

  const target = new URL(url);
  const useHttps = target.protocol === "https:";
  const transport = useHttps ? https : http;
  const agent = useHttps ? HTTPS_AGENT : HTTP_AGENT;

  return await new Promise<JsonHttpResponse>((resolve, reject) => {
    const req = transport.request(
      {
        protocol: target.protocol,
        hostname: target.hostname,
        port: target.port || (useHttps ? 443 : 80),
        path: `${target.pathname}${target.search}`,
        method: options.method,
        headers: options.headers,
        agent,
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (chunk: Buffer | string) => {
          chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
        });
        res.on("end", () => {
          resolve(new BufferedJsonResponse(res.statusCode ?? 0, Buffer.concat(chunks).toString("utf-8")));
        });
      },
    );

    req.on("error", reject);

    let abortHandler: (() => void) | undefined;
    if (options.signal) {
      if (options.signal.aborted) {
        req.destroy(createAbortError());
      } else {
        abortHandler = () => req.destroy(createAbortError());
        options.signal.addEventListener("abort", abortHandler, { once: true });
      }
    }

    req.on("close", () => {
      if (abortHandler && options.signal) {
        options.signal.removeEventListener("abort", abortHandler);
      }
    });

    if (options.body) {
      req.write(options.body);
    }
    req.end();
  });
}

function createAbortError(): Error {
  const error = new Error("Request aborted");
  error.name = "AbortError";
  return error;
}

async function serializeFetchJson(response: Response & { json?: () => Promise<unknown> }): Promise<string> {
  if (typeof response.json !== "function") {
    return "";
  }
  const payload = await response.json();
  return payload == null ? "" : JSON.stringify(payload);
}
