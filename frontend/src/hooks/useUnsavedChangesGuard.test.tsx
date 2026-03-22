import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useUnsavedChangesGuard } from "./useUnsavedChangesGuard";

function GuardHarness({
  isDirty,
  onSave,
  onDiscard,
}: {
  isDirty: boolean;
  onSave: () => Promise<void> | void;
  onDiscard: () => void;
}): JSX.Element {
  const guard = useUnsavedChangesGuard({ isDirty, onSave, onDiscard });

  return (
    <div>
      <a href="/next">Go next</a>
      <button type="button" onClick={() => void guard.onSaveAndContinue()}>
        Save and continue
      </button>
      <button type="button" onClick={guard.onDiscardAndContinue}>
        Discard and continue
      </button>
      <span>{guard.showPrompt ? "prompt-open" : "prompt-closed"}</span>
    </div>
  );
}

describe("useUnsavedChangesGuard", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/current");
  });

  it("ignores navigation when the form is clean", () => {
    const onSave = vi.fn();
    const onDiscard = vi.fn();
    render(<GuardHarness isDirty={false} onSave={onSave} onDiscard={onDiscard} />);

    fireEvent.click(screen.getByText("Go next"));

    expect(screen.getByText("prompt-closed")).toBeDefined();
    expect(window.location.pathname).toBe("/current");
    expect(onSave).not.toHaveBeenCalled();
    expect(onDiscard).not.toHaveBeenCalled();
  });

  it("opens a prompt for in-app link navigation and saves before continuing", async () => {
    window.history.replaceState({}, "", "/current");
    const onSave = vi.fn().mockResolvedValue(undefined);
    const onDiscard = vi.fn();
    const scrollSpy = vi.spyOn(window.history, "pushState");

    render(<GuardHarness isDirty onSave={onSave} onDiscard={onDiscard} />);

    fireEvent.click(screen.getByText("Go next"));
    expect(screen.getByText("prompt-open")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));

    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(scrollSpy).toHaveBeenCalled();
    expect(window.location.pathname).toBe("/next");
  });

  it("discards and navigates, and installs beforeunload protection when dirty", async () => {
    window.history.replaceState({}, "", "/current");
    const onSave = vi.fn();
    const onDiscard = vi.fn();
    render(<GuardHarness isDirty onSave={onSave} onDiscard={onDiscard} />);

    const event = new Event("beforeunload", { cancelable: true }) as BeforeUnloadEvent;
    Object.defineProperty(event, "returnValue", { writable: true, value: undefined });
    window.dispatchEvent(event);
    expect(event.returnValue).toBe("");

    fireEvent.click(screen.getByText("Go next"));
    fireEvent.click(screen.getByRole("button", { name: "Discard and continue" }));

    await waitFor(() => expect(onDiscard).toHaveBeenCalled());
    expect(window.location.pathname).toBe("/next");
  });
});
