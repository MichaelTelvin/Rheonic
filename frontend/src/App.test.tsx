import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./api/client";
import { TestRouter } from "./test/testRouter";

const {
  mockSetUnauthorizedHandler,
  mockFetchCurrentUser,
  mockLogout,
  mockFetchProjects,
  mockFetchProjectProtect,
} = vi.hoisted(() => ({
  mockSetUnauthorizedHandler: vi.fn(),
  mockFetchCurrentUser: vi.fn(),
  mockLogout: vi.fn(),
  mockFetchProjects: vi.fn(),
  mockFetchProjectProtect: vi.fn(),
}));

vi.mock("./api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("./api/client")>();
  return {
    ...original,
    setUnauthorizedHandler: mockSetUnauthorizedHandler,
    fetchCurrentUser: (...args: unknown[]) => mockFetchCurrentUser(...args),
    logout: (...args: unknown[]) => mockLogout(...args),
    fetchProjects: (...args: unknown[]) => mockFetchProjects(...args),
    fetchProjectProtect: (...args: unknown[]) => mockFetchProjectProtect(...args),
  };
});

vi.mock("./pages/Login", () => {
  return {
    Login: ({ onAuthSuccess }: { onAuthSuccess: (user: { email: string }) => void }) => (
      <button
        type="button"
        onClick={() => onAuthSuccess({ id: "u1", email: "user@example.com", created_at: new Date().toISOString() } as any)}
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
vi.mock("./pages/NotFound", () => ({ NotFound: () => <div>Page not found</div> }));

import { App } from "./App";

describe("App", () => {
  beforeEach(() => {
    mockSetUnauthorizedHandler.mockClear();
    mockFetchCurrentUser.mockReset();
    mockLogout.mockReset();
    mockFetchProjects.mockReset();
    mockFetchProjectProtect.mockReset();
    mockFetchCurrentUser.mockRejectedValue(new ApiError(401, "not authenticated"));
    mockLogout.mockResolvedValue({ status: "ok" });
    mockFetchProjects.mockResolvedValue([{ id: "p1", name: "Demo", created_at: new Date().toISOString() }]);
    mockFetchProjectProtect.mockResolvedValue({
      protect_enabled: false,
      protect_fail_mode: "open",
      apply_clamp: false,
      protect_max_req_per_min: null,
      protect_max_tok_per_min: null,
    });
  });

  it("renders landing on public root with CTA buttons", () => {
    render(
      <TestRouter initialEntries={["/"]}>
        <App />
      </TestRouter>,
    );
    expect(screen.getByRole("heading", { name: "Control your agent traffic before it controls your bill." })).toBeDefined();
    expect(screen.getAllByRole("link", { name: "Quickstart" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Sign in" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Privacy" }).getAttribute("href")).toBe("/privacy");
    expect(screen.getByRole("link", { name: "Terms" }).getAttribute("href")).toBe("/terms");
    expect(screen.getByRole("link", { name: "DPA" }).getAttribute("href")).toBe("/dpa");
  });

  it("renders quickstart page on /quickstart", () => {
    render(
      <TestRouter initialEntries={["/quickstart"]}>
        <App />
      </TestRouter>,
    );
    expect(screen.getByRole("heading", { name: "Quickstart" })).toBeDefined();
    expect(screen.getByText(/npm install/i)).toBeDefined();
    fireEvent.click(screen.getAllByRole("button", { name: "Python" })[0]);
    expect(screen.getByText(/pip install/i)).toBeDefined();
  });

  it("renders privacy page on /privacy", () => {
    render(
      <TestRouter initialEntries={["/privacy"]}>
        <App />
      </TestRouter>,
    );
    expect(screen.getByRole("heading", { name: "Privacy Policy" })).toBeDefined();
    expect(screen.getByText(/We collect account, project, and usage data/i)).toBeDefined();
  });

  it("renders terms page on /terms", () => {
    render(
      <TestRouter initialEntries={["/terms"]}>
        <App />
      </TestRouter>,
    );
    expect(screen.getByRole("heading", { name: "Terms of Use" })).toBeDefined();
    expect(screen.getByText(/Rheonic is provided for business evaluation and operational monitoring/i)).toBeDefined();
  });

  it("renders dpa page on /dpa", () => {
    render(
      <TestRouter initialEntries={["/dpa"]}>
        <App />
      </TestRouter>,
    );
    expect(screen.getByRole("heading", { name: "Data Processing Addendum" })).toBeDefined();
    expect(screen.getByText(/Customer is the data controller/i)).toBeDefined();
  });

  it("renders dashboard after login success", async () => {
    render(
      <TestRouter initialEntries={["/login"]}>
        <App />
      </TestRouter>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Mock Login" }));
    expect(await screen.findByText("Dashboard Page")).toBeDefined();
  });

  it("redirects unauthenticated user from /app to /login", async () => {
    render(
      <TestRouter initialEntries={["/app"]}>
        <App />
      </TestRouter>,
    );
    expect(await screen.findByRole("button", { name: "Mock Login" })).toBeDefined();
  });

  it("redirects authenticated user from /login to /app", async () => {
    mockFetchCurrentUser.mockResolvedValue({
      id: "u1",
      email: "persisted@example.com",
      created_at: new Date().toISOString(),
    });

    render(
      <TestRouter initialEntries={["/login"]}>
        <App />
      </TestRouter>,
    );

    expect(await screen.findByText("Dashboard Page")).toBeDefined();
  });

  it("renders not found page for unknown non-app routes", async () => {
    render(
      <TestRouter initialEntries={["/incidents"]}>
        <App />
      </TestRouter>,
    );

    expect(await screen.findByText("Page not found")).toBeDefined();
  });

  it("renders not found page for unknown app routes", async () => {
    mockFetchCurrentUser.mockResolvedValue({
      id: "u1",
      email: "persisted@example.com",
      created_at: new Date().toISOString(),
    });

    render(
      <TestRouter initialEntries={["/app/unknown"]}>
        <App />
      </TestRouter>,
    );

    expect(await screen.findByText("Page not found")).toBeDefined();
  });

  it("restores authenticated session and signs out through backend logout", async () => {
    mockFetchCurrentUser.mockResolvedValue({
      id: "u1",
      email: "persisted@example.com",
      created_at: new Date().toISOString(),
    });

    render(
      <TestRouter initialEntries={["/app"]}>
        <App />
      </TestRouter>,
    );

    expect(await screen.findByText("Dashboard Page")).toBeDefined();
    expect(screen.getByRole("link", { name: "Visit site" }).getAttribute("href")).toBe("/");
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => {
      expect(mockLogout).toHaveBeenCalled();
    });
    expect(await screen.findByRole("button", { name: "Mock Login" })).toBeDefined();
  });

  it("registers and cleans unauthorized handler", () => {
    const { unmount } = render(
      <TestRouter>
        <App />
      </TestRouter>,
    );
    expect(mockSetUnauthorizedHandler).toHaveBeenCalled();
    unmount();
    expect(mockSetUnauthorizedHandler).toHaveBeenLastCalledWith(null);
  });

  it("routes between sidebar pages", async () => {
    mockFetchCurrentUser.mockResolvedValue({
      id: "u1",
      email: "persisted@example.com",
      created_at: new Date().toISOString(),
    });

    render(
      <TestRouter initialEntries={["/app"]}>
        <App />
      </TestRouter>,
    );

    expect(await screen.findByText("Dashboard Page")).toBeDefined();

    fireEvent.click(screen.getByRole("link", { name: "Projects" }));
    expect(await screen.findByText("Projects Page")).toBeDefined();

    fireEvent.click(screen.getByRole("link", { name: "Keys" }));
    expect(await screen.findByText("Keys Page")).toBeDefined();

    fireEvent.click(screen.getByRole("link", { name: "Alerts" }));
    expect(await screen.findByText("Alerts Page")).toBeDefined();

    fireEvent.click(screen.getByRole("link", { name: "Settings" }));
    expect(await screen.findByText("Protect Page")).toBeDefined();

    fireEvent.click(screen.getByRole("link", { name: "Docs" }));
    expect(await screen.findByText("Architecture Page")).toBeDefined();
  });
});
