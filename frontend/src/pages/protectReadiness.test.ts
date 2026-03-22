import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  fetchProjectProtect: vi.fn(),
  fetchProjectWebhook: vi.fn(),
  fetchProjectProviders: vi.fn(),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual("../api/client");
  return {
    ...actual,
    fetchProjectProtect: (...args: unknown[]) => mocks.fetchProjectProtect(...args),
    fetchProjectWebhook: (...args: unknown[]) => mocks.fetchProjectWebhook(...args),
    fetchProjectProviders: (...args: unknown[]) => mocks.fetchProjectProviders(...args),
  };
});

import { getProtectReadiness } from "./protectReadiness";

describe("getProtectReadiness", () => {
  it("returns true readiness flags when config and traffic are present", async () => {
    mocks.fetchProjectProtect.mockResolvedValue({
      protect_max_req_per_min: 10,
      protect_max_tok_per_min: 20,
    });
    mocks.fetchProjectWebhook.mockResolvedValue({
      email_enabled: false,
      enabled: true,
      url: "https://hooks.example.test",
    });
    mocks.fetchProjectProviders.mockResolvedValue(["openai"]);

    await expect(getProtectReadiness("p1")).resolves.toEqual({
      limitsConfigured: true,
      notificationsConfigured: true,
      trafficDetected: true,
    });
  });

  it("returns false readiness flags when config is missing", async () => {
    mocks.fetchProjectProtect.mockResolvedValue({
      protect_max_req_per_min: 0,
      protect_max_tok_per_min: null,
    });
    mocks.fetchProjectWebhook.mockResolvedValue({
      email_enabled: false,
      enabled: false,
      url: "   ",
    });
    mocks.fetchProjectProviders.mockResolvedValue([]);

    await expect(getProtectReadiness("p1")).resolves.toEqual({
      limitsConfigured: false,
      notificationsConfigured: false,
      trafficDetected: false,
    });
  });
});
