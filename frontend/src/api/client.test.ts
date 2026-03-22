import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  createKey,
  createProject,
  deleteProject,
  fetchDeliveryFailures,
  fetchProtectHealth,
  fetchProjectProtect,
  fetchProjectWebhook,
  fetchPublicConfig,
  fetchCurrentUser,
  fetchIncidents,
  fetchMetrics,
  fetchProjectProviders,
  fetchProtectMetrics,
  fetchProjects,
  login,
  logout,
  register,
  resetClientAuthStateForTests,
  resolveIncident,
  revokeKey,
  rotateKey,
  sendFeedback,
  setUnauthorizedHandler,
  testProjectWebhook,
  updateProjectProtect,
  updateProjectWebhook,
} from "./client";

describe("api client", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    resetClientAuthStateForTests();
  });

  it("includes credentials and json content type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          user: { id: "u1", email: "a@b.com" },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await login("a@b.com", "password123");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init.credentials).toBe("include");
  });

  it("invokes unauthorized handler on 401", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: "invalid_token", message: "invalid token" } }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(fetchProjects()).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalled();
  });

  it("retries once after successful refresh on 401", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: { code: "unauthorized", message: "expired" } }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            user: { id: "u1", email: "u@example.com", created_at: new Date().toISOString() },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await fetchProjects();

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[0]?.[1]?.credentials).toBe("include");
    expect(fetchMock.mock.calls[1]?.[1]?.credentials).toBe("include");
    expect(fetchMock.mock.calls[2]?.[1]?.credentials).toBe("include");
  });

  it("refreshes and retries current-user restore on auth me 401", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: { code: "unauthorized", message: "expired" } }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            user: { id: "u1", email: "u@example.com", created_at: new Date().toISOString() },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "u1", email: "u@example.com", created_at: new Date().toISOString() }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await fetchCurrentUser();

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[0]?.[0]).endsWith("/api/v1/auth/me")).toBe(true);
    expect(String(fetchMock.mock.calls[1]?.[0]).endsWith("/api/v1/auth/refresh")).toBe(true);
    expect(String(fetchMock.mock.calls[2]?.[0]).endsWith("/api/v1/auth/me")).toBe(true);
  });

  it("retries stale 401s once after a recent refresh without sending a second refresh request", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-03-11T12:00:00Z"));
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: { code: "unauthorized", message: "expired" } }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ user: { id: "u1", email: "u@example.com" } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: { code: "unauthorized", message: "stale 401" } }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ requests_60s: 1, tokens_60s: 2 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await fetchProjects();
    await fetchMetrics("p1");

    const refreshCalls = fetchMock.mock.calls.filter((call) => String(call[0]).endsWith("/api/v1/auth/refresh"));
    expect(refreshCalls).toHaveLength(1);
    vi.useRealTimers();
  });

  it("uses structured error payload message and code", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: "project_exists", message: "project name already exists" } }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    await expect(createProject("Demo")).rejects.toMatchObject({ status: 409, code: "project_exists" });
  });

  it("falls back to detail string on error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "rate limit exceeded" }), {
          status: 429,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    await expect(fetchMetrics("p1")).rejects.toMatchObject({ message: "rate limit exceeded" });
  });

  it("calls expected endpoint paths and methods", async () => {
    const fetchMock = vi.fn().mockImplementation(
      async () => new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await register("a@b.com", "password123");
    await login("a@b.com", "password123");
    await fetchCurrentUser();
    await logout();
    await fetchMetrics("p 1");
    await fetchMetrics("p 1", "openai");
    await fetchProtectMetrics("p 1", "openai");
    await fetchProjectProviders("p1");
    await fetchIncidents("p/1");
    await fetchIncidents("p/1", "openai");
    await fetchIncidents("p/1", "openai", "resolved");
    await resolveIncident("inc#1");
    await createProject("Project");
    await createKey("p1", "prod");
    await revokeKey("k1");
    await rotateKey("k2");

    const calledPaths = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(calledPaths.some((path) => path.endsWith("/api/v1/auth/register"))).toBe(true);
    expect(calledPaths.some((path) => path.endsWith("/api/v1/auth/login"))).toBe(true);
    expect(calledPaths.some((path) => path.endsWith("/api/v1/auth/me"))).toBe(true);
    expect(calledPaths.some((path) => path.endsWith("/api/v1/auth/logout"))).toBe(true);
    expect(calledPaths.some((path) => path.includes("/api/v1/metrics/realtime?project_id=p%201"))).toBe(true);
    expect(calledPaths.some((path) => path.includes("/api/v1/metrics/realtime?project_id=p%201&provider=openai"))).toBe(true);
    expect(calledPaths.some((path) => path.includes("/api/v1/metrics/protect?project_id=p%201&provider=openai"))).toBe(true);
    expect(calledPaths.some((path) => path.endsWith("/api/v1/projects/p1/providers"))).toBe(true);
    expect(calledPaths.some((path) => path.includes("/api/v1/incidents?project_id=p%2F1"))).toBe(true);
    expect(calledPaths.some((path) => path.includes("/api/v1/incidents?project_id=p%2F1&provider=openai"))).toBe(true);
    expect(calledPaths.some((path) => path.includes("/api/v1/incidents?project_id=p%2F1&provider=openai&status=resolved"))).toBe(true);
    expect(calledPaths.some((path) => path.includes("/api/v1/incidents/inc%231/resolve"))).toBe(true);
    expect(calledPaths.some((path) => path.endsWith("/api/v1/projects/p1/keys"))).toBe(true);
    expect(calledPaths.some((path) => path.endsWith("/api/v1/keys/k1/revoke"))).toBe(true);
    expect(calledPaths.some((path) => path.endsWith("/api/v1/keys/k2/rotate"))).toBe(true);
  });

  it("covers remaining project protect/webhook/public helpers and query variants", async () => {
    const fetchMock = vi.fn().mockImplementation(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (method === "POST" && init?.body === undefined) {
        return new Response(JSON.stringify({ status: "success", status_code: 204 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ status: "ok", providers: ["openai"], public_contact_email: "contact@rheonic.dev" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await fetchProtectHealth("p1");
    await fetchProtectHealth("p1", "google");
    await fetchDeliveryFailures("p1");
    await fetchDeliveryFailures("p1", "email");
    await fetchProjectProtect("p1");
    await updateProjectProtect("p1", {
      protect_enabled: true,
      protect_fail_mode: "closed",
      apply_clamp: true,
      protect_max_req_per_min: 10,
      protect_max_tok_per_min: 20,
    });
    await fetchProjectWebhook("p1");
    await updateProjectWebhook("p1", {
      enabled: true,
      email_enabled: false,
      url: "https://example.com/hook",
    });
    await testProjectWebhook("p1");
    await testProjectWebhook("p1", { url: "https://example.com/override" });
    await deleteProject("p1");
    await sendFeedback({ message: "hello", report_type: "bug" });
    await fetchPublicConfig();

    const called = fetchMock.mock.calls.map((call) => ({
      path: String(call[0]),
      method: (call[1]?.method ?? "GET") as string,
      body: call[1]?.body,
    }));

    expect(called.some((call) => call.path.includes("/api/v1/metrics/protect/health?project_id=p1"))).toBe(true);
    expect(called.some((call) => call.path.includes("/api/v1/metrics/protect/health?project_id=p1&provider=google"))).toBe(true);
    expect(called.some((call) => call.path.includes("/api/v1/metrics/delivery-failures?project_id=p1&kind=webhook"))).toBe(true);
    expect(called.some((call) => call.path.includes("/api/v1/metrics/delivery-failures?project_id=p1&kind=email"))).toBe(true);
    expect(called.some((call) => call.path.endsWith("/api/v1/projects/p1/protect") && call.method === "GET")).toBe(true);
    expect(called.some((call) => call.path.endsWith("/api/v1/projects/p1/protect") && call.method === "PUT")).toBe(true);
    expect(called.some((call) => call.path.endsWith("/api/v1/projects/p1/webhook") && call.method === "GET")).toBe(true);
    expect(called.some((call) => call.path.endsWith("/api/v1/projects/p1/webhook") && call.method === "PUT")).toBe(true);
    expect(called.some((call) => call.path.endsWith("/api/v1/projects/p1/webhook/test") && call.method === "POST" && call.body === undefined)).toBe(true);
    expect(called.some((call) => call.path.endsWith("/api/v1/projects/p1/webhook/test") && call.method === "POST" && String(call.body).includes("override"))).toBe(true);
    expect(called.some((call) => call.path.endsWith("/api/v1/projects/p1") && call.method === "DELETE")).toBe(true);
    expect(called.some((call) => call.path.endsWith("/api/v1/feedback") && call.method === "POST")).toBe(true);
    expect(called.some((call) => call.path.endsWith("/api/v1/public-config"))).toBe(true);
  });
});
