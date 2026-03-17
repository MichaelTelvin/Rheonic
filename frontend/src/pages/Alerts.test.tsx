import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  useProjectContext: vi.fn(),
  useAuthContext: vi.fn(),
  fetchProjectWebhook: vi.fn(),
  fetchProjectProtect: vi.fn(),
  updateProjectWebhook: vi.fn(),
  testProjectWebhook: vi.fn(),
  showAppToast: vi.fn(),
}));

vi.mock("../context/ProjectContext", () => ({
  useProjectContext: () => mocks.useProjectContext(),
}));

vi.mock("../context/AuthContext", () => ({
  useAuthContext: () => mocks.useAuthContext(),
}));

vi.mock("../components/AppToastHost", () => ({
  showAppToast: (...args: unknown[]) => mocks.showAppToast(...args),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual("../api/client");
  return {
    ...actual,
    fetchProjectWebhook: (...args: unknown[]) => mocks.fetchProjectWebhook(...args),
    fetchProjectProtect: (...args: unknown[]) => mocks.fetchProjectProtect(...args),
    updateProjectWebhook: (...args: unknown[]) => mocks.updateProjectWebhook(...args),
    testProjectWebhook: (...args: unknown[]) => mocks.testProjectWebhook(...args),
  };
});

import { Alerts } from "./Alerts";

describe("Alerts webhook settings", () => {
  beforeEach(() => {
    mocks.useProjectContext.mockReturnValue({
      projectId: "p1",
      projects: [{ id: "p1", name: "Demo", created_at: new Date().toISOString() }],
      projectError: null,
      loadingProjects: false,
      setProjectId: vi.fn(),
      reloadProjects: vi.fn(),
    });
    mocks.useAuthContext.mockReturnValue({
      isAuthenticated: true,
      sessionResolved: true,
      user: { id: "u1", email: "user@example.com", created_at: new Date().toISOString() },
      signOut: vi.fn(),
    });
    mocks.fetchProjectWebhook.mockResolvedValue({
      enabled: true,
      email_enabled: true,
      url: "https://hooks.example.test/rheonic",
      has_secret: true,
      last_status: null,
      last_at: null,
      last_error: null,
    });
    mocks.fetchProjectProtect.mockResolvedValue({
      protect_enabled: true,
      protect_fail_mode: "open",
      apply_clamp: false,
      protect_max_req_per_min: null,
      protect_max_tok_per_min: null,
    });
    mocks.updateProjectWebhook.mockResolvedValue({
      enabled: true,
      email_enabled: true,
      url: "https://hooks.example.test/rheonic",
      has_secret: true,
      last_status: null,
      last_at: null,
      last_error: null,
    });
    mocks.testProjectWebhook.mockResolvedValue({ status: "queued" });
    mocks.showAppToast.mockReset();
  });

  it("does not render a custom payload editor", async () => {
    render(<Alerts />);
    await screen.findByRole("button", { name: "Save alerts" });

    expect(screen.queryByLabelText("Custom payload")).toBeNull();
    expect(document.getElementById("payload-editor")).toBeNull();
    expect(screen.queryByLabelText("Secret")).toBeNull();
    expect(screen.getByRole("button", { name: "View payload" })).toBeTruthy();
  });

  it("saves webhook settings without payload template json", async () => {
    render(<Alerts />);
    await screen.findByRole("button", { name: "Save alerts" });

    fireEvent.click(screen.getByRole("button", { name: "Save alerts" }));

    await waitFor(() => expect(mocks.updateProjectWebhook).toHaveBeenCalled());
    expect(mocks.updateProjectWebhook.mock.calls[0][1]).toEqual({
      enabled: true,
      email_enabled: true,
      url: "https://hooks.example.test/rheonic",
    });
  });

  it("tests webhook without payload template json", async () => {
    mocks.fetchProjectWebhook
      .mockResolvedValueOnce({
        enabled: true,
        email_enabled: true,
        url: "https://hooks.example.test/rheonic",
        has_secret: true,
        last_status: null,
        last_at: null,
        last_error: null,
      })
      .mockResolvedValue({
        enabled: true,
        email_enabled: true,
        url: "https://hooks.example.test/rheonic",
        has_secret: true,
        last_status: "success",
        last_at: new Date().toISOString(),
        last_error: null,
      });

    render(<Alerts />);
    await screen.findByRole("button", { name: "Save alerts" });
    fireEvent.click(screen.getByRole("button", { name: "Test webhook" }));

    await waitFor(() => expect(mocks.testProjectWebhook).toHaveBeenCalled());
    expect(mocks.testProjectWebhook.mock.calls[0][1]).toEqual({
      url: "https://hooks.example.test/rheonic",
    });
    expect(mocks.updateProjectWebhook).not.toHaveBeenCalled();
  });

  it("opens sample payload modal and copies json", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    render(<Alerts />);
    await screen.findByRole("button", { name: "Save alerts" });

    fireEvent.click(screen.getByRole("button", { name: "View payload" }));
    expect(
      screen.getByRole("heading", { name: "Sample payload for protection warn event" }),
    ).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Copy JSON" }));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
  });
});
