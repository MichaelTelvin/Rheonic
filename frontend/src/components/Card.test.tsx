import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Card } from "./Card";

describe("Card", () => {
  it("renders children and merges classes", () => {
    const { container } = render(
      <Card className="custom">
        <span>Body</span>
      </Card>,
    );
    const section = container.querySelector("section");
    expect(section?.className.includes("card")).toBe(true);
    expect(section?.className.includes("custom")).toBe(true);
    expect(container.textContent).toContain("Body");
  });
});
