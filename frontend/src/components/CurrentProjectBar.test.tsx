import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  useProjectContext: vi.fn(),
  fetchProjectProtect: vi.fn(),
}));

vi.mock("../context/ProjectContext", () => ({
  useProjectContext: () => mocks.useProjectContext(),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual("../api/client");
  return {
    ...actual,
    fetchProjectProtect: (...args: unknown[]) => mocks.fetchProjectProtect(...args),
  };
});

import { CurrentProjectBar } from "./CurrentProjectBar";

describe("CurrentProjectBar", () => {
  beforeEach(() => {
    mocks.fetchProjectProtect.mockReset();
    mocks.useProjectContext.mockReturnValue({
      loadingProjects: false,
      projectError: null,
      projectId: "p1",
      projects: [
        { id: "p1", name: "dev" },
        { id: "p2", name: "prod" },
      ],
      setProjectId: vi.fn(),
    });
  });

  it("loads and shows protect mode for the selected project", async () => {
    mocks.fetchProjectProtect.mockResolvedValue({ protect_enabled: true });

    render(<CurrentProjectBar />);

    await waitFor(() => expect(screen.getByLabelText("Mode Protect")).toBeDefined());
  });

  it("falls back to Observe when protect settings fail to load", async () => {
    mocks.fetchProjectProtect.mockRejectedValue(new Error("boom"));

    render(<CurrentProjectBar />);

    await waitFor(() => expect(screen.getByLabelText("Mode Observe")).toBeDefined());
  });

  it("updates selected project and reacts to mode update events", async () => {
    const setProjectId = vi.fn();
    mocks.useProjectContext.mockReturnValue({
      loadingProjects: false,
      projectError: "Project sync delayed",
      projectId: "p1",
      projects: [
        { id: "p1", name: "dev" },
        { id: "p2", name: "prod" },
      ],
      setProjectId,
    });
    mocks.fetchProjectProtect.mockResolvedValue({ protect_enabled: false });

    render(<CurrentProjectBar />);

    fireEvent.change(screen.getByLabelText("Current project"), { target: { value: "p2" } });
    expect(setProjectId).toHaveBeenCalledWith("p2");
    expect(screen.getByText("Project sync delayed")).toBeDefined();

    await waitFor(() => expect(screen.getByLabelText("Mode Observe")).toBeDefined());

    window.dispatchEvent(
      new CustomEvent("rheonic:protect-mode-updated", {
        detail: { projectId: "p1", protect_enabled: true },
      }),
    );

    await waitFor(() => expect(screen.getByLabelText("Mode Protect")).toBeDefined());

    window.dispatchEvent(
      new CustomEvent("rheonic:protect-mode-updated", {
        detail: { projectId: "p2", protect_enabled: false },
      }),
    );
    expect(screen.getByLabelText("Mode Protect")).toBeDefined();
  });
});
