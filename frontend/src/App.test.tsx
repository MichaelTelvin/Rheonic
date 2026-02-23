import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockSetUnauthorizedHandler, mockFetchProjects, mockFetchProjectProtect } = vi.hoisted(() => ({
  mockSetUnauthorizedHandler: vi.fn(),
  mockFetchProjects: vi.fn(),
  mockFetchProjectProtect: vi.fn(),
}));

vi.mock("./api/client", () => {
  return {
    setUnauthorizedHandler: mockSetUnauthorizedHandler,
    fetchProjects: (...args: unknown[]) => mockFetchProjects(...args),
    fetchProjectProtect: (...args: unknown[]) => mockFetchProjectProtect(...args),
  };
});

vi.mock("./pages/Login", () => {
  return {
    Login: ({
      onAuthSuccess,
    }: {
      onAuthSuccess: (auth: { access_token: string; refresh_token: string; user: { email: string } }) => void;
    }) => (
      <button
        type="button"
        onClick={() =>
          onAuthSuccess({ access_token: "token-1", refresh_token: "refresh-1", user: { email: "user@example.com" } } as any)
        }
      >
        Mock Login
      </button>
    ),
  };
});

vi.mock("./pages/Dashboard", () => ({ Dashboard: () => <div>Dashboard Page</div> }));
vi.mock("./pages/Projects", () => ({ Projects: () => <div>Projects Page</div> }));
vi.mock("./pages/Keys", () => ({ Keys: () => <div>Keys Page</div> }));
vi.mock("./pages/Alerts", () => ({ Alerts: () => <div>Alerts Page</div> }));
vi.mock("./pages/Protect", () => ({ Protect: () => <div>Protect Page</div> }));
vi.mock("./pages/Architecture", () => ({ Architecture: () => <div>Architecture Page</div> }));
vi.mock("./pages/Incidents", () => ({ Incidents: () => <div>Incidents Page</div> }));

import { App } from "./App";
import { frontendConfig } from "./config";

describe("App", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    mockSetUnauthorizedHandler.mockClear();
    mockFetchProjects.mockReset();
    mockFetchProjectProtect.mockReset();
    mockFetchProjects.mockResolvedValue([{ id: "p1", name: "Demo", created_at: new Date().toISOString() }]);
    mockFetchProjectProtect.mockResolvedValue({
      protect_enabled: false,
      protect_fail_mode: "open",
      protect_max_req_per_min: null,
      protect_max_tok_per_min: null,
      protect_decision_timeout_ms: 100,
    });
  });

  it("renders login when token is missing", () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole("button", { name: "Mock Login" })).toBeDefined();
  });

  it("stores auth payload and renders dashboard after login success", async () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Mock Login" }));

    expect(window.sessionStorage.getItem(frontendConfig.authTokenStorageKey)).toBe("token-1");
    expect(window.sessionStorage.getItem(frontendConfig.authRefreshTokenStorageKey)).toBe("refresh-1");
    expect(window.sessionStorage.getItem(frontendConfig.authUserStorageKey)).toContain("user@example.com");
    expect(await screen.findByText("Dashboard Page")).toBeDefined();
  });

  it("renders authenticated layout from existing storage and signs out", async () => {
    window.sessionStorage.setItem(frontendConfig.authTokenStorageKey, "token-2");
    window.sessionStorage.setItem(frontendConfig.authRefreshTokenStorageKey, "refresh-2");
    window.sessionStorage.setItem(
      frontendConfig.authUserStorageKey,
      JSON.stringify({ id: "u1", email: "persisted@example.com", created_at: new Date().toISOString() }),
    );

    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Dashboard Page")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => {
      expect(window.sessionStorage.getItem(frontendConfig.authTokenStorageKey)).toBeNull();
    });
    expect(screen.getByRole("button", { name: "Mock Login" })).toBeDefined();
  });

  it("registers and cleans unauthorized handler", () => {
    const { unmount } = render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    expect(mockSetUnauthorizedHandler).toHaveBeenCalled();
    unmount();
    expect(mockSetUnauthorizedHandler).toHaveBeenLastCalledWith(null);
  });

  it("routes between sidebar pages", async () => {
    window.sessionStorage.setItem(frontendConfig.authTokenStorageKey, "token-2");
    window.sessionStorage.setItem(frontendConfig.authRefreshTokenStorageKey, "refresh-2");
    window.sessionStorage.setItem(
      frontendConfig.authUserStorageKey,
      JSON.stringify({ id: "u1", email: "persisted@example.com", created_at: new Date().toISOString() }),
    );

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Dashboard Page")).toBeDefined();

    fireEvent.click(screen.getByRole("link", { name: "Projects" }));
    expect(await screen.findByText("Projects Page")).toBeDefined();

    fireEvent.click(screen.getByRole("link", { name: "Keys" }));
    expect(await screen.findByText("Keys Page")).toBeDefined();

    fireEvent.click(screen.getByRole("link", { name: "Alerts" }));
    expect(await screen.findByText("Alerts Page")).toBeDefined();

    fireEvent.click(screen.getByRole("link", { name: "Mode" }));
    expect(await screen.findByText("Protect Page")).toBeDefined();

    fireEvent.click(screen.getByRole("link", { name: "Documentation" }));
    expect(await screen.findByText("Architecture Page")).toBeDefined();
  });
});
