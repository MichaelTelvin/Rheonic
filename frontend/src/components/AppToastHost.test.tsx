import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppToastHost, showAppToast } from "./AppToastHost";

describe("AppToastHost", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows a toast for trimmed messages and auto-hides it", () => {
    vi.useFakeTimers();
    render(<AppToastHost />);

    act(() => {
      showAppToast("  Saved  ");
    });

    expect(screen.getByRole("status").textContent).toContain("Saved");

    act(() => {
      vi.advanceTimersByTime(2200);
    });

    expect(screen.queryByRole("status")).toBeNull();
  });

  it("ignores blank toast messages", () => {
    render(<AppToastHost />);

    act(() => {
      showAppToast("   ");
    });

    expect(screen.queryByRole("status")).toBeNull();
  });
});
