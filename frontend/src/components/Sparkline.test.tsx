import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Sparkline } from "./Sparkline";

describe("Sparkline", () => {
  it("renders fallback midpoint line for single point", () => {
    const { container } = render(<Sparkline values={[3]} stroke="#fff" width={100} height={20} />);
    const polyline = container.querySelector("polyline");
    expect(polyline?.getAttribute("points")).toBe("0,10 100,10");
  });

  it("renders line points for multiple values", () => {
    const { container } = render(<Sparkline values={[1, 3, 2]} stroke="#fff" width={100} height={20} />);
    const points = container.querySelector("polyline")?.getAttribute("points") ?? "";
    expect(points.split(" ").length).toBe(3);
  });
});
