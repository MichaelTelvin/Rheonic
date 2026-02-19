import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockSetUnauthorizedHandler } = vi.hoisted(() => ({
  mockSetUnauthorizedHandler: vi.fn(),
}));

vi.mock("./api/client", () => {
  return {
    setUnauthorizedHandler: mockSetUnauthorizedHandler,
  };
});

vi.mock("./pages/Login", () => {
  return {
    Login: ({ onAuthSuccess }: { onAuthSuccess: (auth: { access_token: string; user: { email: string } }) => void }) => (
      <button
        type="button"
        onClick={() => onAuthSuccess({ access_token: "token-1", user: { email: "user@example.com" } } as any)}
      >
        Mock Login
      </button>
    ),
  };
});

vi.mock("./pages/Dashboard", () => {
  return {
    Dashboard: ({ userEmail, onSignOut }: { userEmail?: string | null; onSignOut?: () => void }) => (
      <div>
        <span>Mock Dashboard {userEmail}</span>
        <button type="button" onClick={onSignOut}>
          Mock Sign Out
        </button>
      </div>
    ),
  };
});

import { App } from "./App";
import { frontendConfig } from "./config";

describe("App", () => {
  beforeEach(() => {
    window.localStorage.clear();
    mockSetUnauthorizedHandler.mockClear();
  });

  it("renders login when token is missing", () => {
    render(<App />);
    expect(screen.getByRole("button", { name: "Mock Login" })).toBeDefined();
  });

  it("stores auth payload and renders dashboard after login success", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Mock Login" }));

    expect(window.localStorage.getItem(frontendConfig.authTokenStorageKey)).toBe("token-1");
    expect(window.localStorage.getItem(frontendConfig.authUserStorageKey)).toContain("user@example.com");
    expect(screen.getByText("Mock Dashboard user@example.com")).toBeDefined();
  });

  it("renders dashboard from existing local storage and signs out", () => {
    window.localStorage.setItem(frontendConfig.authTokenStorageKey, "token-2");
    window.localStorage.setItem(
      frontendConfig.authUserStorageKey,
      JSON.stringify({ id: "u1", email: "persisted@example.com", created_at: new Date().toISOString() }),
    );

    render(<App />);
    expect(screen.getByText("Mock Dashboard persisted@example.com")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Mock Sign Out" }));
    expect(window.localStorage.getItem(frontendConfig.authTokenStorageKey)).toBeNull();
    expect(screen.getByRole("button", { name: "Mock Login" })).toBeDefined();
  });

  it("registers and cleans unauthorized handler", () => {
    const { unmount } = render(<App />);
    expect(mockSetUnauthorizedHandler).toHaveBeenCalled();
    unmount();
    expect(mockSetUnauthorizedHandler).toHaveBeenLastCalledWith(null);
  });
});
