import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QuickstartPage } from "./QuickstartPage";
import { TestRouter } from "../test/testRouter";

class MockIntersectionObserver {
  public static instance: MockIntersectionObserver | null = null;
  private readonly callback: IntersectionObserverCallback;

  public constructor(callback: IntersectionObserverCallback) {
    this.callback = callback;
    MockIntersectionObserver.instance = this;
  }

  public observe(): void {}

  public disconnect(): void {}

  public trigger(target: Element, ratio = 0.7): void {
    this.callback(
      [
        {
          isIntersecting: true,
          intersectionRatio: ratio,
          target,
        } as IntersectionObserverEntry,
      ],
      this as unknown as IntersectionObserver,
    );
  }
}

describe("QuickstartPage", () => {
  beforeEach(() => {
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver as unknown as typeof IntersectionObserver);
  });

  it("switches runtimes/providers and updates the code snippets", async () => {
    render(
      <TestRouter initialEntries={["/quickstart"]}>
        <QuickstartPage />
      </TestRouter>,
    );

    expect(screen.getByText(/npm install @rheonic\/sdk/i)).toBeDefined();

    fireEvent.click(screen.getAllByRole("button", { name: "Python" })[0]);
    expect(screen.getByText(/pip install rheonic-sdk --pre/i)).toBeDefined();

    fireEvent.click(screen.getAllByRole("button", { name: "Anthropic" })[0]);
    expect(screen.getAllByText(/claude-3-5-sonnet-latest/i).length).toBeGreaterThan(0);

    fireEvent.click(screen.getAllByRole("button", { name: "Google" })[0]);
    expect(screen.getAllByText(/gemini-1.5-pro/i).length).toBeGreaterThan(0);
  });

  it("updates the active TOC section and handles smooth scrolling clicks", async () => {
    const scrollIntoView = vi.fn();

    render(
      <TestRouter initialEntries={["/quickstart"]}>
        <QuickstartPage />
      </TestRouter>,
    );

    const protectSection = document.getElementById("protect");
    expect(protectSection).not.toBeNull();
    Object.defineProperty(protectSection!, "scrollIntoView", {
      value: scrollIntoView,
      configurable: true,
    });

    MockIntersectionObserver.instance?.trigger(protectSection!);
    await waitFor(() =>
      expect(screen.getByRole("link", { name: "Enable Protect mode" }).className).toContain("is-active"),
    );

    fireEvent.click(screen.getByRole("link", { name: "Enable Protect mode" }));
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
  });

  it("renders provider-specific protect snippets for both runtimes", () => {
    render(
      <TestRouter initialEntries={["/quickstart"]}>
        <QuickstartPage />
      </TestRouter>,
    );

    expect(screen.getByText(/instrumentOpenAI/i)).toBeDefined();
    expect(screen.getAllByText(/gpt-4o-mini/i).length).toBeGreaterThan(0);

    fireEvent.click(screen.getAllByRole("button", { name: "Anthropic" })[0]);
    expect(screen.getByText(/instrumentAnthropic/i)).toBeDefined();

    fireEvent.click(screen.getAllByRole("button", { name: "Google" })[0]);
    expect(screen.getByText(/GoogleGenAI/i)).toBeDefined();
    expect(screen.getByText(/instrumentGoogle/i)).toBeDefined();
    expect(screen.getByText(/models\.generateContent/i)).toBeDefined();

    fireEvent.click(screen.getAllByRole("button", { name: "Python" })[1]);
    expect(screen.getByText(/instrument_google/i)).toBeDefined();
    expect(screen.getByText(/models\.generate_content/i)).toBeDefined();

    fireEvent.click(screen.getAllByRole("button", { name: "Anthropic" })[0]);
    expect(screen.getByText(/instrument_anthropic/i)).toBeDefined();

    fireEvent.click(screen.getAllByRole("button", { name: "OpenAI" })[0]);
    expect(screen.getByText(/instrument_openai/i)).toBeDefined();
  });

  it("ignores TOC clicks when the target section is missing", () => {
    const replaceState = vi.spyOn(window.history, "replaceState");

    render(
      <TestRouter initialEntries={["/quickstart"]}>
        <QuickstartPage />
      </TestRouter>,
    );

    const nextLink = screen.getByRole("link", { name: "Next step" });
    document.getElementById("next")?.remove();

    fireEvent.click(nextLink);

    expect(replaceState).not.toHaveBeenCalled();
  });
});
