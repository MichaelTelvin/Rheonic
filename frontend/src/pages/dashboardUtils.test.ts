import { describe, expect, it, vi } from "vitest";

import { formatRelative, formatTime, humanizeIncidentType } from "./dashboardUtils";

describe("dashboardUtils", () => {
  it("returns placeholder for invalid or missing times", () => {
    expect(formatTime(null)).toBe("--");
    expect(formatTime("not-a-date")).toBe("--");
  });

  it("formats incident type labels", () => {
    expect(humanizeIncidentType("retry_storm")).toBe("Retry storm");
    expect(humanizeIncidentType("block")).toBe("Block");
  });

  it("formats relative time in seconds, minutes, and hours", () => {
    const now = new Date("2026-02-17T12:00:00.000Z").getTime();
    vi.spyOn(Date, "now").mockReturnValue(now);

    expect(formatRelative("2026-02-17T11:59:45.000Z")).toBe("15s ago");
    expect(formatRelative("2026-02-17T11:55:00.000Z")).toBe("5m ago");
    expect(formatRelative("2026-02-17T10:00:00.000Z")).toBe("2h ago");
    expect(formatRelative("bad-date")).toBe("Unknown");
  });
});
