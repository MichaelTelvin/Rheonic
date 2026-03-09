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
  const mockedFetch = getMockedFetchOverride();
  if (mockedFetch) {
    const response = await mockedFetch(url, {
      method: options.method,
      headers: options.headers,
      body: options.body,
      signal: options.signal,
    });
    return {
      ok: response.ok,
      status: response.status,
      json: async () => await response.json(),
    };
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

function getMockedFetchOverride(): typeof fetch | null {
  if (typeof globalThis.fetch !== "function") {
    return null;
  }
  const source = Function.prototype.toString.call(globalThis.fetch);
  if (source.includes("[native code]")) {
    return null;
  }
  return globalThis.fetch.bind(globalThis);
}
