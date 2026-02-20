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
    fetchProtectMetrics: vi.fn(),
    fetchProtectHealth: vi.fn(),
    resolveIncident: vi.fn(),
    createProject: vi.fn(),
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
    fetchProtectMetrics: (...args: unknown[]) => mocks.fetchProtectMetrics(...args),
    fetchProtectHealth: (...args: unknown[]) => mocks.fetchProtectHealth(...args),
    resolveIncident: (...args: unknown[]) => mocks.resolveIncident(...args),
    createProject: (...args: unknown[]) => mocks.createProject(...args),
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
    mocks.fetchProtectMetrics.mockReset();
    mocks.fetchProtectHealth.mockReset();
    mocks.resolveIncident.mockReset();
    mocks.createProject.mockReset();
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
      warn_60m: 0,
      block_60m: 0,
      decision_timeouts_60m: 0,
      decision_latency_p50_60m_ms: null,
      decision_latency_p95_60m_ms: null,
      last: null,
    });
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
});
