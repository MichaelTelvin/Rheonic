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

describe("Alerts payload editor", () => {
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
      payload_template_json: "{\"text\": \"{{event}}\"}",
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
      payload_template_json: "{\"text\": \"{{event}}\"}",
      last_status: null,
      last_at: null,
      last_error: null,
    });
    mocks.testProjectWebhook.mockResolvedValue({ status: "queued" });
    mocks.showAppToast.mockReset();
  });

  it("loads saved payload template into the editor", async () => {
    render(<Alerts />);
    const toggle = await screen.findByRole("switch", { name: "Use custom payload" });
    expect((toggle as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("Payload template") as HTMLTextAreaElement).value).toContain("\"text\": \"{{event}}\"");
  });

  it("blocks save when payload template json is invalid", async () => {
    render(<Alerts />);
    const input = await screen.findByLabelText("Payload template");
    fireEvent.change(input, { target: { value: "{\"text\":" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Save" })[1]);

    expect(mocks.updateProjectWebhook).not.toHaveBeenCalled();
    expect(await screen.findByText("Payload template must be valid JSON.")).toBeDefined();
  });

  it("sends the draft payload template on webhook test", async () => {
    mocks.fetchProjectWebhook
      .mockResolvedValueOnce({
        enabled: true,
        email_enabled: true,
        url: "https://hooks.example.test/rheonic",
        has_secret: true,
        payload_template_json: "{\"text\": \"{{event}}\"}",
        last_status: null,
        last_at: null,
        last_error: null,
      })
      .mockResolvedValue({
        enabled: true,
        email_enabled: true,
        url: "https://hooks.example.test/rheonic",
        has_secret: true,
        payload_template_json: "{\"text\": \"{{event}}\"}",
        last_status: "success",
        last_at: new Date().toISOString(),
        last_error: null,
      });

    render(<Alerts />);
    const input = await screen.findByLabelText("Payload template");
    fireEvent.change(input, { target: { value: "{\"message\":\"draft {{event}} {{project_id}}\"}" } });
    fireEvent.click(screen.getByRole("button", { name: "Test webhook" }));

    await waitFor(() => expect(mocks.testProjectWebhook).toHaveBeenCalled());
    expect(mocks.testProjectWebhook.mock.calls[0][1]).toEqual({
      payload_template_json: "{\"message\":\"draft {{event}} {{project_id}}\"}",
    });
  });

  it("updates preview when preview event changes", async () => {
    render(<Alerts />);
    await screen.findByLabelText("Payload preview");
    fireEvent.change(screen.getByLabelText("Payload template"), {
      target: { value: "{\"message\":\"{{event}} {{incident_type}}\"}" },
    });
    fireEvent.change(screen.getByLabelText("Preview event"), { target: { value: "incident.block" } });

    await waitFor(() => {
      expect((screen.getByLabelText("Payload preview") as HTMLTextAreaElement).value).toContain("incident.block cap_breach");
    });
  });
});
