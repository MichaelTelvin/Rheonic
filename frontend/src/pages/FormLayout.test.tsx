import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  useProjectContext: vi.fn(),
  listKeys: vi.fn(),
  fetchProjectWebhook: vi.fn(),
  fetchProjectProtect: vi.fn(),
}));

vi.mock("../context/ProjectContext", () => ({
  useProjectContext: () => mocks.useProjectContext(),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual("../api/client");
  return {
    ...actual,
    listKeys: (...args: unknown[]) => mocks.listKeys(...args),
    fetchProjectWebhook: (...args: unknown[]) => mocks.fetchProjectWebhook(...args),
    fetchProjectProtect: (...args: unknown[]) => mocks.fetchProjectProtect(...args),
  };
});

import { Alerts } from "./Alerts";
import { Keys } from "./Keys";
import { Projects } from "./Projects";
import { Protect } from "./Protect";

describe("Form column layout", () => {
  beforeEach(() => {
    mocks.useProjectContext.mockReturnValue({
      projectId: "p1",
      projects: [{ id: "p1", name: "Demo", created_at: new Date().toISOString() }],
      projectError: null,
      loadingProjects: false,
      setProjectId: vi.fn(),
      reloadProjects: vi.fn(),
    });
    mocks.listKeys.mockResolvedValue([]);
    mocks.fetchProjectWebhook.mockResolvedValue({
      enabled: false,
      url: null,
      has_secret: false,
      last_status: null,
      last_at: null,
      last_error: null,
    });
    mocks.fetchProjectProtect.mockResolvedValue({
      protect_enabled: false,
      protect_fail_mode: "open",
      apply_clamp: false,
      protect_max_req_per_min: null,
      protect_max_tok_per_min: null,
      protect_decision_timeout_ms: 100,
    });
  });

  it("constrains Projects form", () => {
    render(<Projects />);
    expect(screen.getByTestId("projects-form-column").className).toContain("form-column");
  });

  it("constrains Keys form", async () => {
    render(<Keys />);
    const node = await screen.findByTestId("keys-form-column");
    expect(node.className).toContain("form-column");
  });

  it("constrains Alerts form", async () => {
    render(<Alerts />);
    const node = await screen.findByTestId("alerts-form-column");
    expect(node.className).toContain("form-column");
  });

  it("constrains Protect form", async () => {
    render(<Protect />);
    const node = await screen.findByTestId("protect-form-column");
    expect(node.className).toContain("protect-settings-grid");
  });

  it("renders accessible info tooltips for per-provider limits", async () => {
    render(<Protect />);
    const infoButtons = await screen.findAllByRole("button", { name: "More info" });
    expect(infoButtons).toHaveLength(3);

    fireEvent.focus(infoButtons[0]);
    expect(screen.getByRole("tooltip").textContent).toContain("Applied per provider.");

    fireEvent.blur(infoButtons[0]);
    fireEvent.focus(infoButtons[2]);
    expect(screen.getByRole("tooltip").textContent).toBe("Apply output token clamp when near limit");
  });

  it("disables clamp toggle in Observe mode and enables it in Protect mode", async () => {
    render(<Protect />);
    const toggle = await screen.findByRole("switch");
    expect(toggle.getAttribute("disabled")).not.toBeNull();

    cleanup();
    mocks.fetchProjectProtect.mockResolvedValueOnce({
      protect_enabled: true,
      protect_fail_mode: "open",
      apply_clamp: false,
      protect_max_req_per_min: null,
      protect_max_tok_per_min: null,
      protect_decision_timeout_ms: 100,
    });
    render(<Protect />);
    const toggleEnabled = await screen.findByRole("switch");
    expect(toggleEnabled.getAttribute("disabled")).toBeNull();
  });
});
