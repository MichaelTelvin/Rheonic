import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  useProjectContext: vi.fn(),
  fetchProjectProtect: vi.fn(),
  sendFeedback: vi.fn(),
  showAppToast: vi.fn(),
}));

vi.mock("../context/ProjectContext", () => ({
  useProjectContext: () => mocks.useProjectContext(),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual("../api/client");
  return {
    ...actual,
    fetchProjectProtect: (...args: unknown[]) => mocks.fetchProjectProtect(...args),
    sendFeedback: (...args: unknown[]) => mocks.sendFeedback(...args),
  };
});

vi.mock("./AppToastHost", () => ({
  showAppToast: (...args: unknown[]) => mocks.showAppToast(...args),
}));

import { FeedbackModal } from "./FeedbackModal";

describe("FeedbackModal", () => {
  beforeEach(() => {
    mocks.useProjectContext.mockReturnValue({ projectId: "p1" });
    mocks.fetchProjectProtect.mockResolvedValue({ protect_enabled: true });
    mocks.sendFeedback.mockResolvedValue({ status: "accepted" });
    mocks.showAppToast.mockReset();
  });

  it("does not render when closed", () => {
    const { container } = render(<FeedbackModal open={false} onClose={vi.fn()} />);
    expect(container.innerHTML).toBe("");
  });

  it("loads project mode and sends a bug report", async () => {
    const onClose = vi.fn();
    render(<FeedbackModal open={true} onClose={onClose} />);
    await waitFor(() => expect(mocks.fetchProjectProtect).toHaveBeenCalledWith("p1"));

    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: "A bug happened" },
    });
    fireEvent.change(screen.getByLabelText("Email (optional)"), {
      target: { value: "user@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send report" }));

    await waitFor(() => expect(mocks.sendFeedback).toHaveBeenCalled());
    await waitFor(() =>
      expect(mocks.sendFeedback.mock.calls[0][0]).toMatchObject({
        report_type: "bug",
        message: "A bug happened",
        email: "user@example.com",
        project_id: "p1",
        mode: "protect",
      }),
    );
    expect(mocks.showAppToast).toHaveBeenCalledWith("Report sent. Thank you.");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("falls back to observe mode when protect settings fail to load", async () => {
    mocks.fetchProjectProtect.mockRejectedValue(new Error("no protect"));
    render(<FeedbackModal open={true} onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Type"), {
      target: { value: "feedback" },
    });
    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: "Please improve this" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send report" }));

    await waitFor(() => expect(mocks.sendFeedback).toHaveBeenCalled());
    expect(mocks.sendFeedback.mock.calls[0][0]).toMatchObject({
      report_type: "feedback",
      mode: "observe",
    });
  });

  it("shows an error toast when send fails", async () => {
    mocks.sendFeedback.mockRejectedValue(new Error("send failed"));
    render(<FeedbackModal open={true} onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: "Broken" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send report" }));

    await waitFor(() => expect(mocks.showAppToast).toHaveBeenCalledWith("Failed to send report. Try again."));
  });

  it("rejects invalid screenshot types and oversized files", async () => {
    render(<FeedbackModal open={true} onClose={vi.fn()} />);
    const input = screen.getByLabelText("Screenshot (optional)");

    fireEvent.change(input, {
      target: { files: [new File(["bad"], "bad.txt", { type: "text/plain" })] },
    });
    expect(mocks.showAppToast).toHaveBeenCalledWith("Screenshot must be an image.");

    const bigFile = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "big.png", { type: "image/png" });
    fireEvent.change(input, {
      target: { files: [bigFile] },
    });
    expect(mocks.showAppToast).toHaveBeenCalledWith("Screenshot must be 5 MB or smaller.");
  });
});
