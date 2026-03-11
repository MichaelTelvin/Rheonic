import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  createKey,
  createProject,
  fetchCurrentUser,
  fetchIncidents,
  fetchMetrics,
  fetchProjectProviders,
  fetchProtectMetrics,
  fetchProjects,
  login,
  logout,
  register,
  resolveIncident,
  revokeKey,
  rotateKey,
  setUnauthorizedHandler,
} from "./client";

describe("api client", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    setUnauthorizedHandler(null);
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
});
