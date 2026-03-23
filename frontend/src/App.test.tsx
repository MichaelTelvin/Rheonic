import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./api/client";
import { App } from "./App";
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
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        const docs: Record<string, string> = {
          "/docs/privacy.md": "# Privacy Policy\n\nWe collect account, project, and usage data needed to operate Rheonic.",
          "/docs/terms.md": "# Terms of Use\n\nRheonic is provided for business evaluation and operational monitoring of LLM traffic.",
          "/docs/dpa.md": "# Data Processing Addendum\n\nCustomer is the data controller.",
        };
        const body = docs[url];

        if (!body) {
          return Promise.resolve(new Response("Not found", { status: 404 }));
        }

        return Promise.resolve(
          new Response(body, {
            status: 200,
            headers: { "Content-Type": "text/markdown" },
          }),
        );
      }),
    );
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

  it("renders privacy page on /privacy", async () => {
    render(
      <TestRouter initialEntries={["/privacy"]}>
        <App />
      </TestRouter>,
    );
    expect(await screen.findByRole("heading", { name: "Privacy Policy" })).toBeDefined();
    expect(await screen.findByText(/We collect account, project, and usage data/i)).toBeDefined();
  });

  it("renders terms page on /terms", async () => {
    render(
      <TestRouter initialEntries={["/terms"]}>
        <App />
      </TestRouter>,
    );
    expect(await screen.findByRole("heading", { name: "Terms of Use" })).toBeDefined();
    expect(await screen.findByText(/Rheonic is provided for business evaluation and operational monitoring/i)).toBeDefined();
  });

  it("renders dpa page on /dpa", async () => {
    render(
      <TestRouter initialEntries={["/dpa"]}>
        <App />
      </TestRouter>,
    );
    expect(await screen.findByRole("heading", { name: "Data Processing Addendum" })).toBeDefined();
    expect(await screen.findByText(/Customer is the data controller/i)).toBeDefined();
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

  it("does not probe auth on a cold login-page refresh", async () => {
    render(
      <TestRouter initialEntries={["/login"]}>
        <App />
      </TestRouter>,
    );

    expect(await screen.findByRole("button", { name: "Mock Login" })).toBeDefined();
    expect(mockFetchCurrentUser).not.toHaveBeenCalled();
  });

  it("does not probe auth on a cold landing-page refresh", async () => {
    render(
      <TestRouter initialEntries={["/"]}>
        <App />
      </TestRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Control your agent traffic before it controls your bill." })).toBeDefined();
    expect(mockFetchCurrentUser).not.toHaveBeenCalled();
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
    window.sessionStorage.setItem(
      "auth_user_cache",
      JSON.stringify({
        id: "u1",
        email: "persisted@example.com",
        created_at: new Date().toISOString(),
      }),
    );
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
    mockFetchCurrentUser.mockResolvedValueOnce({
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

  it("keeps the last known session during non-401 restore failures", async () => {
    window.sessionStorage.setItem(
      "auth_user_cache",
      JSON.stringify({
        id: "u1",
        email: "persisted@example.com",
        created_at: new Date().toISOString(),
      }),
    );
    mockFetchCurrentUser.mockRejectedValueOnce(new ApiError(503, "backend unavailable"));

    render(
      <TestRouter initialEntries={["/app"]}>
        <App />
      </TestRouter>,
    );

    expect(await screen.findByText("Dashboard Page")).toBeDefined();
  });

  it("clears the cached session on real unauthorized restore failures", async () => {
    window.sessionStorage.setItem(
      "auth_user_cache",
      JSON.stringify({
        id: "u1",
        email: "persisted@example.com",
        created_at: new Date().toISOString(),
      }),
    );
    mockFetchCurrentUser.mockRejectedValueOnce(new ApiError(401, "not authenticated"));

    render(
      <TestRouter initialEntries={["/app"]}>
        <App />
      </TestRouter>,
    );

    expect(await screen.findByRole("button", { name: "Mock Login" })).toBeDefined();
    expect(window.sessionStorage.getItem("auth_user_cache")).toBeNull();
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
