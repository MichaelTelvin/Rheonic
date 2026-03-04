import { fetchProjectProtect, fetchProjectProviders, fetchProjectWebhook } from "../api/client";

export interface ProtectReadiness {
  limitsConfigured: boolean;
  notificationsConfigured: boolean;
  trafficDetected: boolean;
}

export async function getProtectReadiness(projectId: string): Promise<ProtectReadiness> {
  const [protect, webhook, providers] = await Promise.all([
    fetchProjectProtect(projectId),
    fetchProjectWebhook(projectId),
    fetchProjectProviders(projectId),
  ]);

  const limitsConfigured = Boolean(
    (protect.protect_max_req_per_min ?? 0) > 0 && (protect.protect_max_tok_per_min ?? 0) > 0,
  );
  const notificationsConfigured = Boolean(webhook.email_enabled || (webhook.enabled && (webhook.url ?? "").trim()));
  const trafficDetected = providers.length > 0;

  return {
    limitsConfigured,
    notificationsConfigured,
    trafficDetected,
  };
}
