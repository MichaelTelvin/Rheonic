import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  useProjectContext: vi.fn(),
  listKeys: vi.fn(),
  createKey: vi.fn(),
  revokeKey: vi.fn(),
  rotateKey: vi.fn(),
  showAppToast: vi.fn(),
}));

vi.mock("../context/ProjectContext", () => ({
  useProjectContext: () => mocks.useProjectContext(),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual("../api/client");
  return {
    ...actual,
    listKeys: (...args: unknown[]) => mocks.listKeys(...args),
    createKey: (...args: unknown[]) => mocks.createKey(...args),
    revokeKey: (...args: unknown[]) => mocks.revokeKey(...args),
    rotateKey: (...args: unknown[]) => mocks.rotateKey(...args),
  };
});

vi.mock("../components/AppToastHost", () => ({
  showAppToast: (...args: unknown[]) => mocks.showAppToast(...args),
}));

import { Keys } from "./Keys";

const keyItem = {
  id: "k1",
  name: "dev",
  last4: "Zj9M",
  created_at: new Date().toISOString(),
  status: "active" as const,
  revoked_at: null,
};

describe("Keys page", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
    mocks.useProjectContext.mockReturnValue({ projectId: "p1" });
    mocks.listKeys.mockResolvedValue([keyItem]);
    mocks.createKey.mockResolvedValue({ key: "rk_live", key_id: "k2", name: "production", last4: "live", created_at: new Date().toISOString() });
    mocks.rotateKey.mockResolvedValue({ key: "rk_rotated", key_id: "k1", name: "dev", last4: "ated", created_at: new Date().toISOString() });
    mocks.revokeKey.mockResolvedValue(undefined);
    mocks.showAppToast.mockReset();
  });

  it("renders empty state when no project is selected", () => {
    mocks.useProjectContext.mockReturnValue({ projectId: null });
    render(<Keys />);
    expect(screen.getByText("Select a project to manage ingest keys.")).toBeTruthy();
  });

  it("creates, rotates, revokes, and copies keys", async () => {
    render(<Keys />);
    await screen.findByText("Existing keys");

    fireEvent.change(screen.getByLabelText("Key label (environment)"), {
      target: { value: "production" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create key" }));
    await waitFor(() => expect(mocks.createKey).toHaveBeenCalledWith("p1", "production"));

    fireEvent.click(screen.getByRole("button", { name: "Rotate" }));
    await waitFor(() => expect(mocks.rotateKey).toHaveBeenCalledWith("k1"));

    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(mocks.revokeKey).toHaveBeenCalledWith("k1"));

    fireEvent.click(await screen.findByRole("button", { name: "Copy key" }));
    await waitFor(() => expect(mocks.showAppToast).toHaveBeenCalledWith("Copied to clipboard"));
  });

  it("shows validation errors for empty key labels", async () => {
    render(<Keys />);
    await screen.findByText("Existing keys");
    fireEvent.click(screen.getByRole("button", { name: "Create key" }));
    expect(await screen.findByText("Key label is required.")).toBeTruthy();
  });
});
