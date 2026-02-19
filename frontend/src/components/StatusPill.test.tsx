import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusPill } from "./StatusPill";

describe("StatusPill", () => {
  it("renders connected state", () => {
    render(<StatusPill connected={true} />);
    const node = screen.getByText("API Connected");
    expect(node.className.includes("connected")).toBe(true);
  });

  it("renders disconnected state", () => {
    render(<StatusPill connected={false} />);
    const node = screen.getByText("API Disconnected");
    expect(node.className.includes("disconnected")).toBe(true);
  });
});
