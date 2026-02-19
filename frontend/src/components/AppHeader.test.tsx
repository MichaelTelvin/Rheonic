import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppHeader } from "./AppHeader";

describe("AppHeader", () => {
  it("renders brand text", () => {
    render(<AppHeader />);
    expect(screen.getByText("LLMTokenBurnGuard")).toBeDefined();
  });

  it("renders user email and signs out", () => {
    const onSignOut = vi.fn();
    render(<AppHeader userEmail="user@example.com" onSignOut={onSignOut} />);
    expect(screen.getByText("user@example.com")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(onSignOut).toHaveBeenCalled();
  });
});
