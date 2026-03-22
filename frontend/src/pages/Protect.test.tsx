import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  useProjectContext: vi.fn(),
  fetchProjectProtect: vi.fn(),
  updateProjectProtect: vi.fn(),
  deleteProject: vi.fn(),
  getProtectReadiness: vi.fn(),
  showAppToast: vi.fn(),
}));

vi.mock("../context/ProjectContext", () => ({
  useProjectContext: () => mocks.useProjectContext(),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual("../api/client");
  return {
    ...actual,
    fetchProjectProtect: (...args: unknown[]) => mocks.fetchProjectProtect(...args),
    updateProjectProtect: (...args: unknown[]) => mocks.updateProjectProtect(...args),
    deleteProject: (...args: unknown[]) => mocks.deleteProject(...args),
  };
});

vi.mock("./protectReadiness", async () => {
  const actual = await vi.importActual("./protectReadiness");
  return {
    ...actual,
    getProtectReadiness: (...args: unknown[]) => mocks.getProtectReadiness(...args),
  };
});

vi.mock("../components/AppToastHost", () => ({
  showAppToast: (...args: unknown[]) => mocks.showAppToast(...args),
}));

import { Protect } from "./Protect";

function getProtectInput(id: string): HTMLInputElement {
  const input = document.getElementById(id);
  if (!(input instanceof HTMLInputElement)) {
    throw new Error(`Expected input #${id}`);
  }
  return input;
}

describe("Protect page", () => {
  beforeEach(() => {
    mocks.fetchProjectProtect.mockReset();
    mocks.updateProjectProtect.mockReset();
    mocks.deleteProject.mockReset();
    mocks.getProtectReadiness.mockReset();
    mocks.showAppToast.mockReset();

    mocks.useProjectContext.mockReturnValue({
      projectId: "p1",
      projects: [
        { id: "p1", name: "dev" },
        { id: "p2", name: "prod" },
      ],
      setProjectId: vi.fn(),
      reloadProjects: vi.fn().mockResolvedValue([{ id: "p2", name: "prod" }]),
    });

    mocks.fetchProjectProtect.mockResolvedValue({
      protect_enabled: false,
      protect_fail_mode: "open",
      apply_clamp: false,
      protect_max_req_per_min: null,
      protect_max_tok_per_min: null,
    });
    mocks.updateProjectProtect.mockResolvedValue({
      protect_enabled: false,
      protect_fail_mode: "closed",
      apply_clamp: true,
      protect_max_req_per_min: 50,
      protect_max_tok_per_min: 500,
    });
    mocks.getProtectReadiness.mockResolvedValue({
      limitsConfigured: false,
      notificationsConfigured: false,
      trafficDetected: false,
    });
    window.localStorage.clear();
  });

  it("renders the empty state when no project is selected", () => {
    mocks.useProjectContext.mockReturnValue({
      projectId: null,
      projects: [],
      setProjectId: vi.fn(),
      reloadProjects: vi.fn(),
    });

    render(<Protect />);

    expect(screen.getByText("Select a project to configure protection rules.")).toBeDefined();
  });

  it("opens readiness modal when switching from observe to protect with warnings", async () => {
    render(<Protect />);

    fireEvent.change(await screen.findByLabelText("Project mode"), { target: { value: "protect" } });

    expect(await screen.findByRole("heading", { name: "Enable Protect mode?" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Open settings" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Open Quickstart" })).toBeDefined();
  });

  it("saves settings and shows the enabled toast when protect is turned on", async () => {
    mocks.fetchProjectProtect.mockResolvedValue({
      protect_enabled: false,
      protect_fail_mode: "open",
      apply_clamp: false,
      protect_max_req_per_min: 5,
      protect_max_tok_per_min: 50,
    });
    mocks.getProtectReadiness.mockResolvedValue({
      limitsConfigured: true,
      notificationsConfigured: true,
      trafficDetected: true,
    });
    mocks.updateProjectProtect.mockResolvedValue({
      protect_enabled: true,
      protect_fail_mode: "closed",
      apply_clamp: true,
      protect_max_req_per_min: 25,
      protect_max_tok_per_min: 250,
    });

    render(<Protect />);

    const modeSelect = await screen.findByLabelText("Project mode") as HTMLSelectElement;
    fireEvent.change(modeSelect, { target: { value: "protect" } });
    const enableProtectButton = screen.queryByRole("button", { name: "Enable Protect" });
    if (enableProtectButton) {
      fireEvent.click(enableProtectButton);
    }
    await waitFor(() => expect(modeSelect.value).toBe("protect"));
    fireEvent.change(getProtectInput("protect-max-req"), { target: { value: "25" } });
    fireEvent.change(getProtectInput("protect-max-tok"), { target: { value: "250" } });
    fireEvent.click(screen.getByRole("radio", { name: "Block LLM request" }));
    fireEvent.click(screen.getByRole("switch"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mocks.updateProjectProtect).toHaveBeenCalledWith(
        "p1",
        expect.objectContaining({
          protect_enabled: true,
          protect_fail_mode: "closed",
          apply_clamp: true,
          protect_max_req_per_min: 25,
          protect_max_tok_per_min: 250,
        }),
      ),
    );
    expect(mocks.showAppToast).toHaveBeenCalledWith("Protect enabled");
  });

  it("deletes the current project and selects the next one", async () => {
    const setProjectId = vi.fn();
    const reloadProjects = vi.fn().mockResolvedValue([{ id: "p2", name: "prod" }]);
    mocks.useProjectContext.mockReturnValue({
      projectId: "p1",
      projects: [
        { id: "p1", name: "dev" },
        { id: "p2", name: "prod" },
      ],
      setProjectId,
      reloadProjects,
    });

    render(<Protect />);

    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "delete project" }));

    await waitFor(() => expect(mocks.deleteProject).toHaveBeenCalledWith("p1"));
    expect(setProjectId).toHaveBeenCalledWith("p2");
    expect(mocks.showAppToast).toHaveBeenCalledWith("Project deleted");
  });
});
