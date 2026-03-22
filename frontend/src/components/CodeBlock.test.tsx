import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CodeBlock } from "./CodeBlock";

describe("CodeBlock", () => {
  const writeText = vi.fn();

  beforeEach(() => {
    writeText.mockReset();
    Object.assign(navigator, {
      clipboard: {
        writeText,
      },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("copies code and resets the button label", async () => {
    vi.useFakeTimers();
    writeText.mockResolvedValue(undefined);

    render(<CodeBlock code={"print('ok')"} language="python" />);
    const button = screen.getByRole("button", { name: "Copy" });

    await act(async () => {
      fireEvent.click(button);
      await Promise.resolve();
    });

    expect(writeText).toHaveBeenCalledWith("print('ok')");
    expect(button.textContent).toBe("Copied");

    await actAdvance(1200);
    expect(button.textContent).toBe("Copy");
  });

  it("keeps the copy label when clipboard write fails", async () => {
    writeText.mockRejectedValue(new Error("copy failed"));

    render(<CodeBlock code={"print('ok')"} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));

    await waitFor(() => expect(writeText).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Copy" })).toBeTruthy();
    expect(document.querySelector("code")?.className).toContain("language-text");
  });
});

async function actAdvance(ms: number): Promise<void> {
  await act(async () => {
    vi.advanceTimersByTime(ms);
    await Promise.resolve();
  });
}
