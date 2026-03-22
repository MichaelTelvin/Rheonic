import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Architecture } from "./Architecture";

describe("Architecture page", () => {
  it("renders docs hub cards and chart link", () => {
    render(<Architecture />);

    expect(screen.getByRole("heading", { name: "Documentation" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open charts" }).getAttribute("href")).toContain("chart=incident");
    expect(screen.getAllByRole("link", { name: "Open docs" }).length).toBeGreaterThan(3);
  });
});
