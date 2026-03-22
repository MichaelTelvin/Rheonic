import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UnsavedChangesToast } from "./UnsavedChangesToast";

describe("UnsavedChangesToast", () => {
  it("renders nothing when closed", () => {
    const { container } = render(<UnsavedChangesToast open={false} />);
    expect(container.innerHTML).toBe("");
  });

  it("renders save and discard actions when handlers are present", () => {
    const onSave = vi.fn();
    const onDiscard = vi.fn();

    render(<UnsavedChangesToast open={true} onSave={onSave} onDiscard={onDiscard} />);

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onDiscard).toHaveBeenCalledTimes(1);
  });

  it("shows saving state when busy", () => {
    render(<UnsavedChangesToast open={true} busy={true} onSave={vi.fn()} onDiscard={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Saving..." })).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "Discard" })).toHaveProperty("disabled", true);
  });
});
