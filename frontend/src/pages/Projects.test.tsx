import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { frontendConfig } from "../config";
import { Projects } from "./Projects";

const mocks = vi.hoisted(() => ({
  useProjectContext: vi.fn(),
  createProject: vi.fn(),
  showAppToast: vi.fn(),
}));

vi.mock("../context/ProjectContext", () => ({
  useProjectContext: () => mocks.useProjectContext(),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual("../api/client");
  return {
    ...actual,
    createProject: (...args: unknown[]) => mocks.createProject(...args),
  };
});

vi.mock("../components/AppToastHost", () => ({
  showAppToast: (...args: unknown[]) => mocks.showAppToast(...args),
}));

describe("Projects page", () => {
  beforeEach(() => {
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
    mocks.useProjectContext.mockReturnValue({
      projects: [{ id: "924ed2ab-0000-0000-0000-000000781a", name: "dev", created_at: new Date().toISOString() }],
      projectId: "924ed2ab-0000-0000-0000-000000781a",
      setProjectId: vi.fn(),
      reloadProjects: vi.fn().mockResolvedValue([
        { id: "p2", name: "prod", created_at: new Date().toISOString() },
      ]),
    });
    mocks.createProject.mockResolvedValue({ id: "p2", name: "prod", created_at: new Date().toISOString() });
    mocks.showAppToast.mockReset();
    Object.defineProperty(frontendConfig, "apiBaseUrl", {
      value: "http://localhost:8000",
      configurable: true,
    });
  });

  it("validates project name before creating", async () => {
    render(<Projects />);
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(await screen.findByText("Project name is required.")).toBeTruthy();
    expect(mocks.createProject).not.toHaveBeenCalled();
  });

  it("creates a project and selects it", async () => {
    render(<Projects />);

    fireEvent.change(screen.getByLabelText("Project name"), {
      target: { value: "prod" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));

    await waitFor(() => expect(mocks.createProject).toHaveBeenCalledWith("prod"));
    expect(mocks.showAppToast).toHaveBeenCalledWith("Project created");
  });

  it("copies backend URL and project id", async () => {
    render(<Projects />);

    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(mocks.showAppToast).toHaveBeenCalledWith("URL copied"));
    fireEvent.click(screen.getByRole("button", { name: /Copy project ID for dev/i }));

    await waitFor(() => expect(mocks.showAppToast).toHaveBeenCalledWith("Project ID copied"));
  });
});
