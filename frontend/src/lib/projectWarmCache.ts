import {
  fetchProjectProtect,
  fetchProjectProviders,
  fetchProjectWebhook,
  fetchProtectHealth,
  fetchProtectMetrics,
  listKeys,
  type ProjectProtectSettings,
  type ProjectWebhookSettings,
  type ProtectHealthMetrics,
} from "../api/client";

type ProtectDecisionStats = {
  allowed_60m: number | null;
  clamped_60m: number | null;
  blocked_60m: number | null;
};

export type ProjectWarmState = {
  protectSettings?: ProjectProtectSettings | null;
  webhookSettings?: ProjectWebhookSettings | null;
  providers?: string[];
  hasIngestKey?: boolean;
  protectHealth?: ProtectHealthMetrics | null;
  lastProtectHealthSuccessAt?: string | null;
  protectDecisionStats?: ProtectDecisionStats | null;
};

const projectWarmCache = new Map<string, ProjectWarmState>();
const projectWarmInflight = new Map<string, Promise<void>>();

export function readProjectWarmState(projectId: string | null): ProjectWarmState | null {
  if (!projectId) {
    return null;
  }
  return projectWarmCache.get(projectId) ?? null;
}

export function mergeProjectWarmState(projectId: string, patch: Partial<ProjectWarmState>): void {
  const current = projectWarmCache.get(projectId) ?? {};
  projectWarmCache.set(projectId, {
    ...current,
    ...patch,
  });
}

export async function prefetchProjectWarmState(projectId: string): Promise<void> {
  const existing = projectWarmInflight.get(projectId);
  if (existing) {
    await existing;
    return;
  }

  const task = (async () => {
    const fetchedAt = new Date().toISOString();
    const [protectResult, webhookResult, providersResult, keysResult, healthResult, metricsResult] = await Promise.allSettled([
      fetchProjectProtect(projectId),
      fetchProjectWebhook(projectId),
      fetchProjectProviders(projectId),
      listKeys(projectId),
      fetchProtectHealth(projectId),
      fetchProtectMetrics(projectId),
    ]);

    const patch: Partial<ProjectWarmState> = {};
    if (protectResult.status === "fulfilled") {
      patch.protectSettings = protectResult.value;
    }
    if (webhookResult.status === "fulfilled") {
      patch.webhookSettings = webhookResult.value;
    }
    if (providersResult.status === "fulfilled") {
      patch.providers = providersResult.value;
    }
    if (keysResult.status === "fulfilled") {
      patch.hasIngestKey = keysResult.value.some((key) => key.status === "active");
    }
    if (healthResult.status === "fulfilled") {
      patch.protectHealth = healthResult.value;
      patch.lastProtectHealthSuccessAt = fetchedAt;
    }
    if (metricsResult.status === "fulfilled") {
      patch.protectDecisionStats = {
        allowed_60m: metricsResult.value.allowed_60m,
        clamped_60m: metricsResult.value.clamped_60m,
        blocked_60m: metricsResult.value.blocked_60m,
      };
    }
    mergeProjectWarmState(projectId, patch);
  })().finally(() => {
    projectWarmInflight.delete(projectId);
  });

  projectWarmInflight.set(projectId, task);
  await task;
}
