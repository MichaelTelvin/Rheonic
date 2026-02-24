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
    fetchMetrics: vi.fn(),
    fetchIncidents: vi.fn(),
    fetchProjectProviders: vi.fn(),
    fetchProjectProtect: vi.fn(),
    fetchProtectMetrics: vi.fn(),
    resolveIncident: vi.fn(),
    useProjectContext: vi.fn(),
  };
});

vi.mock("../api/client", () => {
  return {
    ApiError: mocks.ApiError,
    fetchMetrics: (...args: unknown[]) => mocks.fetchMetrics(...args),
    fetchIncidents: (...args: unknown[]) => mocks.fetchIncidents(...args),
    fetchProjectProviders: (...args: unknown[]) => mocks.fetchProjectProviders(...args),
    fetchProjectProtect: (...args: unknown[]) => mocks.fetchProjectProtect(...args),
    fetchProtectMetrics: (...args: unknown[]) => mocks.fetchProtectMetrics(...args),
    resolveIncident: (...args: unknown[]) => mocks.resolveIncident(...args),
  };
});

vi.mock("../context/ProjectContext", () => {
  return {
    useProjectContext: () => mocks.useProjectContext(),
  };
});

import { Dashboard } from "./Dashboard";

describe("Dashboard", () => {
  beforeEach(() => {
    mocks.fetchMetrics.mockReset();
    mocks.fetchIncidents.mockReset();
    mocks.fetchProjectProviders.mockReset();
    mocks.fetchProjectProtect.mockReset();
    mocks.fetchProtectMetrics.mockReset();
    mocks.resolveIncident.mockReset();
    mocks.useProjectContext.mockReset();

    mocks.useProjectContext.mockReturnValue({
      projectId: "p1",
      projects: [{ id: "p1", name: "Demo", created_at: new Date().toISOString() }],
    });
    mocks.fetchMetrics.mockResolvedValue({ requests_60s: 3, tokens_60s: 42 });
    mocks.fetchIncidents.mockResolvedValue([]);
    mocks.fetchProjectProviders.mockResolvedValue(["anthropic", "openai"]);
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
  });

  it("shows empty state when no project is selected", async () => {
    mocks.useProjectContext.mockReturnValue({ projectId: null, projects: [] });
    render(<Dashboard />);
    expect(await screen.findByText("Select a project to see realtime metrics.")).toBeDefined();
  });

  it("loads metrics and incidents for selected project", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(mocks.fetchMetrics).toHaveBeenCalledWith("p1", undefined));
    expect(mocks.fetchIncidents).toHaveBeenCalledWith("p1");
    expect(screen.getByText("Requests (60s)")).toBeDefined();
    expect(screen.getByText("Tokens (60s)")).toBeDefined();
  });

  it("loads provider list and applies provider filter to metrics calls", async () => {
    render(<Dashboard />);

    await waitFor(() => expect(mocks.fetchProjectProviders).toHaveBeenCalledWith("p1"));
    const providerSelect = await screen.findByLabelText("Provider");
    fireEvent.change(providerSelect, { target: { value: "openai" } });

    await waitFor(() => expect(mocks.fetchMetrics).toHaveBeenCalledWith("p1", "openai"));
    expect(mocks.fetchProtectMetrics).toHaveBeenCalledWith("p1", "openai");

    fireEvent.change(providerSelect, { target: { value: "all" } });
    await waitFor(() => expect(mocks.fetchMetrics).toHaveBeenCalledWith("p1", undefined));
  });

  it("resets provider filter to All when project changes", async () => {
    const context = {
      projectId: "p1",
      projects: [{ id: "p1", name: "Demo", created_at: new Date().toISOString() }],
    };
    mocks.useProjectContext.mockImplementation(() => context);
    const { rerender } = render(<Dashboard />);

    const providerSelect = await screen.findByLabelText("Provider");
    fireEvent.change(providerSelect, { target: { value: "openai" } });
    await waitFor(() => expect(mocks.fetchMetrics).toHaveBeenCalledWith("p1", "openai"));

    context.projectId = "p2";
    context.projects = [
      { id: "p1", name: "Demo", created_at: new Date().toISOString() },
      { id: "p2", name: "Two", created_at: new Date().toISOString() },
    ];
    mocks.fetchProjectProviders.mockResolvedValueOnce(["anthropic"]);
    rerender(<Dashboard />);

    await waitFor(() => expect(mocks.fetchMetrics).toHaveBeenCalledWith("p2", undefined));
    expect((screen.getByLabelText("Provider") as HTMLSelectElement).value).toBe("all");
  });

  it("shows forbidden warning when metrics request fails with 403", async () => {
    mocks.fetchMetrics.mockRejectedValue(new mocks.ApiError(403, "forbidden"));
    render(<Dashboard />);
    const metricWarnings = await screen.findAllByText("Metrics request was forbidden.");
    expect(metricWarnings).toHaveLength(2);
  });

  it("renders counters as 0 and percentiles as em-dash when null", async () => {
    render(<Dashboard />);

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

  it("resolves an incident and refreshes list", async () => {
    mocks.fetchIncidents
      .mockResolvedValueOnce([
        {
          id: "inc-1",
          type: "token_burn_rate",
          severity: "medium",
          status: "open",
          created_at: new Date().toISOString(),
          resolved_at: null,
          evidence: {},
        },
      ])
      .mockResolvedValueOnce([]);

    render(<Dashboard />);
    const resolveButton = await screen.findByRole("button", { name: "Resolve" });
    fireEvent.click(resolveButton);

    await waitFor(() => expect(mocks.resolveIncident).toHaveBeenCalledWith("inc-1"));
  });

  it("does not render dashboard config modal buttons", async () => {
    render(<Dashboard />);
    await screen.findByText("Requests (60s)");

    expect(screen.queryByRole("button", { name: "New Project" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Keys" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Alerts" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Enable protection" })).toBeNull();
  });
});
