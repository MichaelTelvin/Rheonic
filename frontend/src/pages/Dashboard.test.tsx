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
    fetchProtectHealth: vi.fn(),
    fetchMetrics: vi.fn(),
    fetchIncidents: vi.fn(),
    fetchProjectProviders: vi.fn(),
    fetchProtectMetrics: vi.fn(),
    fetchDeliveryFailures: vi.fn(),
    listKeys: vi.fn(),
    resolveIncident: vi.fn(),
    useProjectContext: vi.fn(),
  };
});

vi.mock("../api/client", () => {
  return {
    ApiError: mocks.ApiError,
    fetchProtectHealth: (...args: unknown[]) => mocks.fetchProtectHealth(...args),
    fetchMetrics: (...args: unknown[]) => mocks.fetchMetrics(...args),
    fetchIncidents: (...args: unknown[]) => mocks.fetchIncidents(...args),
    fetchProjectProviders: (...args: unknown[]) => mocks.fetchProjectProviders(...args),
    fetchProtectMetrics: (...args: unknown[]) => mocks.fetchProtectMetrics(...args),
    fetchDeliveryFailures: (...args: unknown[]) => mocks.fetchDeliveryFailures(...args),
    listKeys: (...args: unknown[]) => mocks.listKeys(...args),
    resolveIncident: (...args: unknown[]) => mocks.resolveIncident(...args),
  };
});

vi.mock("../context/ProjectContext", () => {
  return {
    useProjectContext: () => mocks.useProjectContext(),
  };
});

import { Dashboard } from "./Dashboard";
import { TestRouter } from "../test/testRouter";

describe("Dashboard", () => {
  beforeEach(() => {
    mocks.fetchMetrics.mockReset();
    mocks.fetchProtectHealth.mockReset();
    mocks.fetchIncidents.mockReset();
    mocks.fetchProjectProviders.mockReset();
    mocks.fetchProtectMetrics.mockReset();
    mocks.fetchDeliveryFailures.mockReset();
    mocks.listKeys.mockReset();
    mocks.resolveIncident.mockReset();
    mocks.useProjectContext.mockReset();

    mocks.useProjectContext.mockReturnValue({
      loadingProjects: false,
      projectId: "p1",
      projects: [{ id: "p1", name: "Demo", created_at: new Date().toISOString() }],
    });
    mocks.fetchMetrics.mockResolvedValue({ requests_60s: 3, tokens_60s: 42 });
    mocks.fetchProtectHealth.mockResolvedValue({ p50_ms: 4, p95_ms: 12, timeouts_30m: 0, timeouts_60m: 0 });
    mocks.fetchIncidents.mockResolvedValue([]);
    mocks.fetchProjectProviders.mockResolvedValue(["anthropic", "openai"]);
    mocks.fetchProtectMetrics.mockResolvedValue({
      allowed_60m: 0,
      clamped_60m: 0,
      blocked_60m: 0,
      decision_timeouts_60m: 0,
      decision_latency_p50_60m_ms: null,
      decision_latency_p95_60m_ms: null,
      last: null,
    });
    mocks.fetchDeliveryFailures.mockResolvedValue({ count: 0, last_attempt_at: null });
    mocks.listKeys.mockResolvedValue([{ id: "k1", name: "Key", status: "active" }]);
  });

  it("shows setup banner when no project is selected", async () => {
    mocks.useProjectContext.mockReturnValue({ loadingProjects: false, projectId: null, projects: [] });
    render(
      <TestRouter>
        <Dashboard />
      </TestRouter>,
    );
    expect(await screen.findByText("Setup required")).toBeDefined();
    expect(screen.getByText(/Create your first project\./i)).toBeDefined();
    expect(screen.getByText(/Generate an ingest key, then follow Quickstart\./i)).toBeDefined();
  });

  it("loads metrics and incidents for selected project", async () => {
    render(
      <TestRouter>
        <Dashboard />
      </TestRouter>,
    );
    await waitFor(() => expect(mocks.fetchMetrics).toHaveBeenCalledWith("p1", undefined));
    expect(mocks.fetchProtectHealth).toHaveBeenCalledWith("p1", undefined);
    expect(mocks.fetchIncidents).toHaveBeenCalledWith("p1", undefined);
    expect(screen.getByText("Requests (60s)")).toBeDefined();
    expect(screen.getByText("Tokens (60s)")).toBeDefined();
  });

  it("loads provider list and applies provider filter to metrics and incidents calls", async () => {
    render(
      <TestRouter>
        <Dashboard />
      </TestRouter>,
    );

    await waitFor(() => expect(mocks.fetchProjectProviders).toHaveBeenCalledWith("p1"));
    const providerSelect = await screen.findByLabelText("Provider");
    fireEvent.change(providerSelect, { target: { value: "openai" } });

    await waitFor(() => expect(mocks.fetchMetrics).toHaveBeenCalledWith("p1", "openai"));
    expect(mocks.fetchProtectHealth).toHaveBeenCalledWith("p1", "openai");
    expect(mocks.fetchProtectMetrics).toHaveBeenCalledWith("p1", "openai");
    expect(mocks.fetchIncidents).toHaveBeenCalledWith("p1", "openai");

    fireEvent.change(providerSelect, { target: { value: "all" } });
    await waitFor(() => expect(mocks.fetchMetrics).toHaveBeenCalledWith("p1", undefined));
  });

  it("resets provider filter to All when project changes", async () => {
    const context = {
      loadingProjects: false,
      projectId: "p1",
      projects: [{ id: "p1", name: "Demo", created_at: new Date().toISOString() }],
    };
    mocks.useProjectContext.mockImplementation(() => context);
    const { rerender } = render(
      <TestRouter>
        <Dashboard />
      </TestRouter>,
    );

    const providerSelect = await screen.findByLabelText("Provider");
    fireEvent.change(providerSelect, { target: { value: "openai" } });
    await waitFor(() => expect(mocks.fetchMetrics).toHaveBeenCalledWith("p1", "openai"));

    context.projectId = "p2";
    context.projects = [
      { id: "p1", name: "Demo", created_at: new Date().toISOString() },
      { id: "p2", name: "Two", created_at: new Date().toISOString() },
    ];
    mocks.fetchProjectProviders.mockResolvedValueOnce(["anthropic"]);
    rerender(
      <TestRouter>
        <Dashboard />
      </TestRouter>,
    );

    await waitFor(() => expect(mocks.fetchMetrics).toHaveBeenCalledWith("p2", undefined));
    expect((screen.getByLabelText("Provider") as HTMLSelectElement).value).toBe("all");
  });

  it("shows global forbidden banner when metrics request fails with 403", async () => {
    mocks.fetchMetrics.mockRejectedValue(new mocks.ApiError(403, "forbidden"));
    render(
      <TestRouter>
        <Dashboard />
      </TestRouter>,
    );
    expect(await screen.findByText("You do not have access to this project's metrics.")).toBeDefined();
  });

  it("renders protect decision counters", async () => {
    render(
      <TestRouter>
        <Dashboard />
      </TestRouter>,
    );

    const allowedLabel = await screen.findByText("Allowed");
    const allowedRow = allowedLabel.closest(".protect-decisions-row");
    expect(allowedRow?.querySelector(".protect-decisions-value")?.textContent).toBe("0");

    const blockedLabel = await screen.findByText("Blocked");
    const blockedRow = blockedLabel.closest(".protect-decisions-row");
    expect(blockedRow?.querySelector(".protect-decisions-value")?.textContent).toBe("0");
  });

  it("renders incidents summary card counts", async () => {
    mocks.fetchIncidents.mockResolvedValueOnce([
      {
        id: "inc-1",
        type: "block",
        status: "open",
        created_at: new Date().toISOString(),
        resolved_at: null,
        evidence: {},
      },
      {
        id: "inc-2",
        type: "retry_storm",
        status: "open",
        created_at: new Date().toISOString(),
        resolved_at: null,
        evidence: {},
      },
    ]);
    render(
      <TestRouter>
        <Dashboard />
      </TestRouter>,
    );
    await screen.findByText("Incident episodes");
    expect(screen.getByText("Block")).toBeDefined();
    expect(screen.getByText("Retry storm")).toBeDefined();
  });

  it("does not render dashboard config modal buttons", async () => {
    render(
      <TestRouter>
        <Dashboard />
      </TestRouter>,
    );
    await screen.findByText("Requests (60s)");

    expect(screen.queryByRole("button", { name: "New Project" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Keys" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Alerts" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Enable protection" })).toBeNull();
  });

  it("shows dismissible webhook issue banner with updated action copy", async () => {
    mocks.fetchDeliveryFailures.mockResolvedValue({ count: 2, last_attempt_at: "2026-03-15T18:00:00Z" });
    render(
      <TestRouter>
        <Dashboard />
      </TestRouter>,
    );

    expect(await screen.findByText("Webhook delivery issues in the last 24 hours")).toBeDefined();
    expect(screen.getByRole("button", { name: "Check URL" })).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    await waitFor(() => expect(screen.queryByText("Webhook delivery issues in the last 24 hours")).toBeNull());
  });
});
