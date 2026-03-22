import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NotFound } from "./NotFound";
import { TestRouter } from "../test/testRouter";

describe("NotFound", () => {
  it("renders public not found links", () => {
    render(
      <TestRouter>
        <NotFound />
      </TestRouter>,
    );

    expect(screen.getByRole("heading", { name: "Page not found" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Go to dashboard" }).getAttribute("href")).toBe("/app");
    expect(screen.getByRole("link", { name: "Go to home" }).getAttribute("href")).toBe("/");
  });

  it("adds the in-app class when requested", () => {
    const { container } = render(
      <TestRouter>
        <NotFound inApp={true} />
      </TestRouter>,
    );

    expect(container.querySelector(".notfound-page-in-app")).toBeTruthy();
  });
});
