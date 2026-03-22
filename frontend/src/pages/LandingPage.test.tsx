import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TestRouter } from "../test/testRouter";
import { LandingPage } from "./LandingPage";

class MockIntersectionObserver {
  public static instance: MockIntersectionObserver | null = null;

  private readonly callback: IntersectionObserverCallback;

  public constructor(callback: IntersectionObserverCallback) {
    this.callback = callback;
    MockIntersectionObserver.instance = this;
  }

  public observe(): void {}

  public disconnect(): void {}

  public trigger(target: Element): void {
    this.callback(
      [{ isIntersecting: true, intersectionRatio: 0.5, target } as IntersectionObserverEntry],
      this as unknown as IntersectionObserver,
    );
  }
}

describe("LandingPage", () => {
  beforeEach(() => {
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver as unknown as typeof IntersectionObserver);
  });

  it("renders marketing CTAs and reveals sections when they enter view", async () => {
    render(
      <TestRouter initialEntries={["/"]}>
        <LandingPage />
      </TestRouter>,
    );

    expect(screen.getAllByRole("link", { name: "Start beta testing" })[0]?.getAttribute("href")).toBe("/login");
    expect(screen.getAllByRole("link", { name: "View quickstart" })[0]?.getAttribute("href")).toBe("/quickstart");

    const revealedSection = screen.getByText("Agentic systems don’t fail quietly.").closest(".reveal-on-scroll");
    expect(revealedSection).not.toBeNull();
    MockIntersectionObserver.instance?.trigger(revealedSection!);

    await waitFor(() => expect(revealedSection?.className).toContain("is-visible"));
  });

  it("renders safely when IntersectionObserver is unavailable", () => {
    vi.stubGlobal("IntersectionObserver", undefined);

    render(
      <TestRouter initialEntries={["/"]}>
        <LandingPage />
      </TestRouter>,
    );

    expect(screen.getByText("Visual flow")).toBeDefined();
    expect(screen.getByText("Control layer")).toBeDefined();
  });
});
