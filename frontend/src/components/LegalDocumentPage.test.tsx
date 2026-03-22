import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LegalDocumentPage from "./LegalDocumentPage";
import { TestRouter } from "../test/testRouter";

describe("LegalDocumentPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("renders markdown content with headings, lists, links, and email tokens", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        [
          "# Privacy",
          "",
          "Lead paragraph with **bold** and `code` and [Docs](https://example.com).",
          "",
          "- first item",
          "- second item",
          "",
          "Contact founder@rheonic.dev",
        ].join("\n"),
        { status: 200, headers: { "Content-Type": "text/markdown" } },
      ),
    );

    render(
      <TestRouter initialEntries={["/privacy"]}>
        <LegalDocumentPage
          title="Privacy"
          description="desc"
          path="/privacy"
          markdownPath="/docs/privacy.md"
        />
      </TestRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Privacy" })).toBeDefined();
    const leadParagraphs = screen.getAllByText((_, element) =>
      element?.tagName.toLowerCase() === "p"
      && (element.textContent?.includes("Lead paragraph with") ?? false),
    );
    expect(leadParagraphs.length).toBeGreaterThan(0);
    expect(screen.getByText("bold")).toBeDefined();
    expect(screen.getByText("code")).toBeDefined();
    expect(screen.getByRole("link", { name: "Docs" }).getAttribute("href")).toBe("https://example.com");
    expect(screen.getByRole("link", { name: "founder@rheonic.dev" }).getAttribute("href")).toBe("mailto:founder@rheonic.dev");
  });

  it("shows a fallback when the document fails to load", async () => {
    vi.mocked(fetch).mockRejectedValue(new Error("network"));

    render(
      <TestRouter initialEntries={["/privacy"]}>
        <LegalDocumentPage
          title="Privacy"
          description="desc"
          path="/privacy"
          markdownPath="/docs/privacy.md"
        />
      </TestRouter>,
    );

    await waitFor(() =>
      expect(screen.getByText("We couldn't load this document right now.")).toBeDefined(),
    );
  });
});
