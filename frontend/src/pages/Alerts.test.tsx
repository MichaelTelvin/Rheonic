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
    expect((screen.getByLabelText("Custom payload (JSON object)") as HTMLTextAreaElement).value).toContain("\"text\": \"{{event}}\"");
    expect(screen.getByText(/Write the JSON body you want to send\./i)).toBeDefined();
  });

  it("blocks save when payload template json is invalid", async () => {
    render(<Alerts />);
    const input = await screen.findByLabelText("Custom payload (JSON object)");
    fireEvent.change(input, { target: { value: "{\"chat_id\":" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(mocks.updateProjectWebhook).not.toHaveBeenCalled();
    expect(await screen.findByText("Custom payload must be a valid JSON object.")).toBeDefined();
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
    const payloadInput = await screen.findByLabelText("Custom payload (JSON object)");
    fireEvent.change(payloadInput, { target: { value: "{\n  \"text\": \"draft {{event}} {{project_id}}\",\n  \"chat_id\": \"123\"\n}" } });
    fireEvent.click(screen.getByRole("button", { name: "Test webhook" }));

    await waitFor(() => expect(mocks.testProjectWebhook).toHaveBeenCalled());
    const payload = mocks.testProjectWebhook.mock.calls[0][1].payload_template_json as string;
    expect(payload).toContain("\"text\":\"draft {{event}} {{project_id}}\"");
    expect(payload).toContain("\"chat_id\":\"123\"");
    expect(payload).toContain("\"rheonic\"");
  });

  it("updates preview when preview event changes", async () => {
    render(<Alerts />);
    const toggle = await screen.findByRole("switch", { name: "Use custom payload" });
    if (!(toggle as HTMLInputElement).checked) {
      fireEvent.click(toggle);
    }
    await screen.findByLabelText("Example body");
    fireEvent.change(screen.getByLabelText("Custom payload (JSON object)"), {
      target: { value: "{\n  \"text\": \"{{event}} {{incident_type}}\"\n}" },
    });
    fireEvent.change(screen.getByLabelText("Preview event"), { target: { value: "incident.block" } });

    await waitFor(() => {
      expect((screen.getByLabelText("Example body") as HTMLTextAreaElement).value).toContain("incident.block cap_breach");
      expect((screen.getByLabelText("Example body") as HTMLTextAreaElement).value).not.toContain("\"rheonic\"");
    });
  });
});
