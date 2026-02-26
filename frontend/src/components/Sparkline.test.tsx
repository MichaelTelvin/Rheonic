import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Sparkline } from "./Sparkline";

describe("Sparkline", () => {
  it("renders fallback midpoint line path for single point", () => {
    const { container } = render(<Sparkline values={[3]} stroke="#fff" width={100} height={20} />);
    const path = container.querySelector("path");
    expect(path?.getAttribute("d")).toBe("M 0 10 L 100 10");
  });

  it("renders smoothed path for multiple values", () => {
    const { container } = render(<Sparkline values={[1, 3, 2]} stroke="#fff" width={100} height={20} />);
    const path = container.querySelector("path")?.getAttribute("d") ?? "";
    expect(path.startsWith("M ")).toBe(true);
    expect(path.includes(" Q ")).toBe(true);
  });
});
