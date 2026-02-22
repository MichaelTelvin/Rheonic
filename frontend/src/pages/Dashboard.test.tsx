import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  class HoistedApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  }
  return {
    ApiError: HoistedApiError,
    fetchProjects: vi.fn(),
    fetchMetrics: vi.fn(),
    fetchIncidents: vi.fn(),
    fetchProjectProtect: vi.fn(),
    fetchProjectWebhook: vi.fn(),
    fetchProtectMetrics: vi.fn(),
    fetchProtectHealth: vi.fn(),
    resolveIncident: vi.fn(),
    createProject: vi.fn(),
    updateProjectWebhook: vi.fn(),
    testProjectWebhook: vi.fn(),
    listKeys: vi.fn(),
    createKey: vi.fn(),
    revokeKey: vi.fn(),
    rotateKey: vi.fn(),
  };
});

vi.mock("../api/client", () => {
  return {
    ApiError: mocks.ApiError,
    fetchProjects: (...args: unknown[]) => mocks.fetchProjects(...args),
    fetchMetrics: (...args: unknown[]) => mocks.fetchMetrics(...args),
    fetchIncidents: (...args: unknown[]) => mocks.fetchIncidents(...args),
    fetchProjectProtect: (...args: unknown[]) => mocks.fetchProjectProtect(...args),
    fetchProjectWebhook: (...args: unknown[]) => mocks.fetchProjectWebhook(...args),
    fetchProtectMetrics: (...args: unknown[]) => mocks.fetchProtectMetrics(...args),
    fetchProtectHealth: (...args: unknown[]) => mocks.fetchProtectHealth(...args),
    resolveIncident: (...args: unknown[]) => mocks.resolveIncident(...args),
    createProject: (...args: unknown[]) => mocks.createProject(...args),
    updateProjectWebhook: (...args: unknown[]) => mocks.updateProjectWebhook(...args),
    testProjectWebhook: (...args: unknown[]) => mocks.testProjectWebhook(...args),
    listKeys: (...args: unknown[]) => mocks.listKeys(...args),
    createKey: (...args: unknown[]) => mocks.createKey(...args),
    revokeKey: (...args: unknown[]) => mocks.revokeKey(...args),
    rotateKey: (...args: unknown[]) => mocks.rotateKey(...args),
  };
});

import { Dashboard } from "./Dashboard";

describe("Dashboard", () => {
  beforeEach(() => {
    window.localStorage.clear();
    mocks.fetchProjects.mockReset();
    mocks.fetchMetrics.mockReset();
    mocks.fetchIncidents.mockReset();
    mocks.fetchProjectProtect.mockReset();
    mocks.fetchProjectWebhook.mockReset();
    mocks.fetchProtectMetrics.mockReset();
    mocks.fetchProtectHealth.mockReset();
    mocks.resolveIncident.mockReset();
    mocks.createProject.mockReset();
    mocks.updateProjectWebhook.mockReset();
    mocks.testProjectWebhook.mockReset();
    mocks.listKeys.mockReset();
    mocks.createKey.mockReset();
    mocks.revokeKey.mockReset();
    mocks.rotateKey.mockReset();
    mocks.fetchMetrics.mockResolvedValue({ requests_60s: 3, tokens_60s: 42 });
    mocks.fetchIncidents.mockResolvedValue([]);
    mocks.fetchProjectProtect.mockResolvedValue({
      protect_enabled: false,
      protect_fail_mode: "open",
      protect_max_req_per_min: null,
      protect_max_tok_per_min: null,
      protect_decision_timeout_ms: 100,
    });
    mocks.fetchProtectMetrics.mockResolvedValue({
      allowed_60m: 0,
      warned_60m: 0,
      blocked_60m: 0,
      decision_timeouts_60m: 0,
      decision_latency_p50_60m_ms: null,
      decision_latency_p95_60m_ms: null,
      last: null,
    });
    mocks.fetchProjectWebhook.mockResolvedValue({
      enabled: false,
      url: null,
      has_secret: false,
      last_status: null,
      last_at: null,
      last_error: null,
    });
    mocks.updateProjectWebhook.mockResolvedValue({
      enabled: false,
      url: null,
      has_secret: false,
      last_status: null,
      last_at: null,
      last_error: null,
    });
    mocks.testProjectWebhook.mockResolvedValue({ status: "queued" });
    mocks.fetchProtectHealth.mockResolvedValue({ p50_ms: null, p95_ms: null, timeouts_60m: 0 });
  });

  it("shows empty onboarding state when no projects exist", async () => {
    mocks.fetchProjects.mockResolvedValue([]);
    render(<Dashboard userEmail="user@example.com" onSignOut={vi.fn()} />);
    expect(await screen.findByText("Create your first project to start collecting metrics.")).toBeDefined();
    expect(screen.getByRole("button", { name: "Create your first project" })).toBeDefined();
  });

  it("auto-selects single project and loads metrics/incidents", async () => {
    mocks.fetchProjects.mockResolvedValue([{ id: "p1", name: "Demo", created_at: new Date().toISOString() }]);
    render(<Dashboard userEmail="user@example.com" onSignOut={vi.fn()} />);

    await waitFor(() => expect(mocks.fetchMetrics).toHaveBeenCalledWith("p1"));
    expect(mocks.fetchIncidents).toHaveBeenCalledWith("p1");
    expect(screen.getByText("Requests (60s)")).toBeDefined();
    expect(screen.getByText("Tokens (60s)")).toBeDefined();
  });

  it("shows forbidden banner when metrics request fails with 403", async () => {
    mocks.fetchProjects.mockResolvedValue([{ id: "p1", name: "Demo", created_at: new Date().toISOString() }]);
    mocks.fetchMetrics.mockRejectedValue(new mocks.ApiError(403, "forbidden"));
    render(<Dashboard userEmail="user@example.com" onSignOut={vi.fn()} />);
    expect(await screen.findByText("Metrics request was forbidden.")).toBeDefined();
  });

  it("opens create-project modal and validates input", async () => {
    mocks.fetchProjects.mockResolvedValue([{ id: "p1", name: "Demo", created_at: new Date().toISOString() }]);
    render(<Dashboard userEmail="user@example.com" onSignOut={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "New Project" }));
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByText("Project name is required.")).toBeDefined();
  });

  it("renders counters as 0 and percentiles as em-dash when null", async () => {
    mocks.fetchProjects.mockResolvedValue([{ id: "p1", name: "Demo", created_at: new Date().toISOString() }]);
    mocks.fetchProtectMetrics.mockResolvedValue({
      allowed_60m: 0,
      warned_60m: 0,
      blocked_60m: 0,
      decision_timeouts_60m: 0,
      decision_latency_p50_60m_ms: null,
      decision_latency_p95_60m_ms: null,
      last: null,
    });
    render(<Dashboard userEmail="user@example.com" onSignOut={vi.fn()} />);

    const allowedLabel = await screen.findByText("Allowed");
    const allowedRow = allowedLabel.closest(".protect-decisions-row");
    expect(allowedRow?.querySelector(".protect-decisions-value")?.textContent).toBe("0");

    const timeoutLabel = await screen.findByText("Timeouts");
    const timeoutRow = timeoutLabel.closest(".protect-decisions-row");
    expect(timeoutRow?.querySelector(".protect-decisions-value")?.textContent).toBe("0");

    const p50Label = await screen.findByText("P50 latency (ms)");
    const p50Row = p50Label.closest(".protect-decisions-row");
    expect(p50Row?.querySelector(".protect-decisions-value")?.textContent).toBe("—");
  });

  it("saves and tests webhook from alerts panel", async () => {
    mocks.fetchProjects.mockResolvedValue([{ id: "p1", name: "Demo", created_at: new Date().toISOString() }]);
    render(<Dashboard userEmail="user@example.com" onSignOut={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "Alerts" }));
    const urlInput = await screen.findByLabelText("Webhook URL");
    fireEvent.change(urlInput, { target: { value: "https://example.test/hook" } });
    fireEvent.click(screen.getByRole("button", { name: "Test webhook" }));
    await waitFor(() =>
      expect(mocks.testProjectWebhook).toHaveBeenCalledWith("p1", {
        url: "https://example.test/hook",
        secret: undefined,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(mocks.updateProjectWebhook).toHaveBeenCalledWith("p1", {
        enabled: false,
        url: "https://example.test/hook",
        secret: null,
      }),
    );
  });
});
