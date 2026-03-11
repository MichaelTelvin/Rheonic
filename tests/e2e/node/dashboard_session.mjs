function readSetCookies(response) {
  if (typeof response.headers.getSetCookie === "function") {
    return response.headers.getSetCookie();
  }
  const raw = response.headers.get("set-cookie");
  if (!raw) {
    return [];
  }
  return raw.split(/,(?=[^;,\s]+=)/g);
}

async function parseResponseBody(response) {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return await response.json();
  }
  return await response.text();
}

export class DashboardSession {
  constructor(baseUrl) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.cookies = new Map();
  }

  async login(email, password) {
    return await this.request("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  }

  async request(path, options = {}, retry = true) {
    const headers = new Headers(options.headers ?? {});
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const cookieHeader = this.cookieHeader();
    if (cookieHeader) {
      headers.set("Cookie", cookieHeader);
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers,
    });
    this.storeCookies(response);

    if (response.status === 401 && retry && !path.startsWith("/api/v1/auth/")) {
      const refreshed = await this.refresh();
      if (refreshed) {
        return await this.request(path, options, false);
      }
    }

    const payload = await parseResponseBody(response);
    if (!response.ok) {
      throw new Error(`API ${path} failed (${response.status}): ${JSON.stringify(payload)}`);
    }
    return payload;
  }

  async refresh() {
    try {
      await this.request("/api/v1/auth/refresh", { method: "POST" }, false);
      return true;
    } catch {
      return false;
    }
  }

  cookieHeader() {
    return Array.from(this.cookies.entries())
      .map(([name, value]) => `${name}=${value}`)
      .join("; ");
  }

  storeCookies(response) {
    for (const setCookie of readSetCookies(response)) {
      const [pair] = setCookie.split(";");
      const separatorIndex = pair.indexOf("=");
      if (separatorIndex <= 0) {
        continue;
      }
      const name = pair.slice(0, separatorIndex).trim();
      const value = pair.slice(separatorIndex + 1).trim();
      if (!value) {
        this.cookies.delete(name);
        continue;
      }
      this.cookies.set(name, value);
    }
  }
}
