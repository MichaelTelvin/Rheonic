import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { IncidentItem } from "./IncidentItem";

const incident = {
  id: "inc-1",
  type: "burn_spike",
  severity: "high" as const,
  status: "open" as const,
  created_at: new Date("2026-02-19T10:00:00Z").toISOString(),
  resolved_at: null,
  evidence: { req_ratio: 10, tok_ratio: 12 },
};

describe("IncidentItem", () => {
  it("toggles details and resolves incident", async () => {
    const onResolve = vi.fn().mockResolvedValue(undefined);
    render(<IncidentItem incident={incident} resolving={false} onResolve={onResolve} />);

    fireEvent.click(screen.getByRole("button", { name: "Show details" }));
    expect(screen.getByText(/"tok_ratio": 12/)).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Resolve" }));
    await waitFor(() => expect(onResolve).toHaveBeenCalledWith("inc-1"));
  });

  it("shows resolving state label", () => {
    render(<IncidentItem incident={incident} resolving={true} onResolve={vi.fn().mockResolvedValue(undefined)} />);
    expect(screen.getByRole("button", { name: "Resolving..." })).toBeDefined();
  });
});
