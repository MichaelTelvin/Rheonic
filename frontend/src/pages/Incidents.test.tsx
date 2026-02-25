import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  fetchIncidents: vi.fn(),
  fetchProjectProviders: vi.fn(),
  resolveIncident: vi.fn(),
  useProjectContext: vi.fn(),
}));

vi.mock("../api/client", () => {
  class HoistedApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  }
  return {
    ApiError: HoistedApiError,
    fetchIncidents: (...args: unknown[]) => mocks.fetchIncidents(...args),
    fetchProjectProviders: (...args: unknown[]) => mocks.fetchProjectProviders(...args),
    resolveIncident: (...args: unknown[]) => mocks.resolveIncident(...args),
  };
});

vi.mock("../context/ProjectContext", () => {
  return {
    useProjectContext: () => mocks.useProjectContext(),
  };
});

import { Incidents } from "./Incidents";

describe("Incidents page", () => {
  beforeEach(() => {
    mocks.fetchIncidents.mockReset();
    mocks.fetchProjectProviders.mockReset();
    mocks.resolveIncident.mockReset();
    mocks.useProjectContext.mockReset();

    mocks.useProjectContext.mockReturnValue({
      projectId: "p1",
      projects: [{ id: "p1", name: "Demo", created_at: new Date().toISOString() }],
    });
    mocks.fetchProjectProviders.mockResolvedValue(["openai", "anthropic"]);
    mocks.fetchIncidents.mockResolvedValue([]);
  });

  it("loads provider options and applies provider/severity/status filters", async () => {
    render(
      <MemoryRouter initialEntries={["/incidents?provider=openai"]}>
        <Incidents />
      </MemoryRouter>,
    );

    await waitFor(() => expect(mocks.fetchIncidents).toHaveBeenCalledWith("p1", "openai", undefined, "open"));

    fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "high" } });
    await waitFor(() => expect(mocks.fetchIncidents).toHaveBeenCalledWith("p1", "openai", "high", "open"));

    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "resolved" } });
    await waitFor(() => expect(mocks.fetchIncidents).toHaveBeenCalledWith("p1", "openai", "high", "resolved"));

    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "all" } });
    await waitFor(() => expect(mocks.fetchIncidents).toHaveBeenCalledWith("p1", undefined, "high", "resolved"));
  });
});
