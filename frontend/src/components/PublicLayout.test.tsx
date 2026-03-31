import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  fetchPublicConfig: vi.fn(),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual("../api/client");
  return {
    ...actual,
    fetchPublicConfig: (...args: unknown[]) => mocks.fetchPublicConfig(...args),
  };
});

import { PublicLayout } from "./PublicLayout";
import { TestRouter } from "../test/testRouter";

describe("PublicLayout", () => {
  beforeEach(() => {
    mocks.fetchPublicConfig.mockReset();
    mocks.fetchPublicConfig.mockResolvedValue({ public_contact_email: "team@rheonic.dev" });
  });

  it("renders marketing footer links, loads contact config, and updates sticky state on scroll", async () => {
    render(
      <TestRouter initialEntries={["/"]}>
        <PublicLayout
          navAuthHref="/login"
          navAuthLabel="Sign in"
          shellClassName="public-shell--marketing"
          showDocsLink={false}
          showBetaBadge
        >
          <div>Marketing content</div>
        </PublicLayout>
      </TestRouter>,
    );

    expect(screen.getByText("Marketing content")).toBeDefined();
    expect(screen.getByText("Beta")).toBeDefined();
    const footer = document.querySelector(".public-footer-landing-legal");
    expect(footer).not.toBeNull();
    expect(within(footer as HTMLElement).getByRole("link", { name: "Quickstart" }).getAttribute("href")).toBe("/quickstart");
    expect(await screen.findByText("team@rheonic.dev")).toBeDefined();

    Object.defineProperty(window, "scrollY", { value: 12, configurable: true });
    fireEvent.scroll(window);

    await waitFor(() => expect(document.querySelector(".public-nav")?.className).toContain("is-scrolled"));
  });

  it("renders quickstart footer variant and falls back to configured contact email on fetch failure", async () => {
    mocks.fetchPublicConfig.mockRejectedValue(new Error("boom"));

    render(
      <TestRouter initialEntries={["/quickstart"]}>
        <PublicLayout
          navAuthHref="/login"
          navAuthLabel="Sign in"
          shellClassName="public-shell--quickstart"
          showHomeLink
          showQuickstartLink={false}
          showDocsLink
          docsLinkLabel="Docs"
        >
          <div>Quickstart content</div>
        </PublicLayout>
      </TestRouter>,
    );

    const footer = document.querySelector(".public-footer-quickstart-legal");
    expect(footer).not.toBeNull();
    expect(within(footer as HTMLElement).getByRole("link", { name: "Home" }).getAttribute("href")).toBe("/");
    expect(within(footer as HTMLElement).getByRole("link", { name: "Docs" }).getAttribute("href")).toBe("/docs/viewer.html?doc=overview");
    expect(within(footer as HTMLElement).getByRole("link", { name: "Privacy" }).getAttribute("href")).toBe("/privacy");
    expect(screen.getByText("© 2026 Rheonic")).toBeDefined();
  });

  it("renders the default footer variant", () => {
    render(
      <TestRouter initialEntries={["/legal"]}>
        <PublicLayout navAuthHref="/login" navAuthLabel="Sign in" showHomeLink showQuickstartLink showDocsLink={false}>
          <div>Default content</div>
        </PublicLayout>
      </TestRouter>,
    );

    const footer = document.querySelector(".public-footer");
    expect(footer).not.toBeNull();
    expect(within(footer as HTMLElement).getByRole("link", { name: "Home" }).getAttribute("href")).toBe("/");
    expect(within(footer as HTMLElement).getByRole("link", { name: "Quickstart" }).getAttribute("href")).toBe("/quickstart");
    expect(within(footer as HTMLElement).getByRole("link", { name: "Sign in" }).getAttribute("href")).toBe("/login");
  });
});
