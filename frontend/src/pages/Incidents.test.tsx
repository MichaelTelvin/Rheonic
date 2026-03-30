import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
import { TestRouter } from "../test/testRouter";

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

  it("loads provider options and applies provider/type/status filters", async () => {
    render(
      <TestRouter initialEntries={["/incidents?provider=openai"]}>
        <Incidents />
      </TestRouter>,
    );

    await waitFor(() => expect(mocks.fetchIncidents).toHaveBeenCalledWith("p1", "openai", "open"));

    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "block" } });
    await waitFor(() => expect(mocks.fetchIncidents).toHaveBeenCalledWith("p1", "openai", "open"));

    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "resolved" } });
    await waitFor(() => expect(mocks.fetchIncidents).toHaveBeenCalledWith("p1", "openai", "resolved"));

    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "all" } });
    await waitFor(() => expect(mocks.fetchIncidents).toHaveBeenCalledWith("p1", undefined, "resolved"));
  });
});
