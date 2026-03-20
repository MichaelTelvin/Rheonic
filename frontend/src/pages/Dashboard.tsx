import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  ApiError,
  fetchDeliveryFailures,
  fetchIncidents,
  fetchMetrics,
  fetchProtectHealth,
  fetchProjectProviders,
  fetchProtectMetrics,
  listKeys,
  type IncidentItem,
  type ProtectHealthMetrics,
  type RealtimeMetrics,
} from "../api/client";
import { Card } from "../components/Card";
import { PulseMeter } from "../components/pulseMeter";
import { frontendConfig } from "../config";
import { useProjectContext } from "../context/ProjectContext";
import { formatNumber, formatTime } from "./dashboardUtils";

function formatProviderLabel(provider: string): string {
  return provider
    .split(/[_-]/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function normalizeProviderValue(provider: string): string {
  return provider.trim().toLowerCase();
}

function formatAlertAttemptTime(iso: string | null): string {
  if (!iso) {
    return "--";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

type SetupStage = "checking" | "no_project" | "no_selection" | "no_ingest_key" | "no_events" | "complete";
type ProtectStatus = "awaiting" | "healthy" | "degraded" | "unavailable";
const DASHBOARD_BANNER_EXIT_MS = 280;
const DASHBOARD_METRICS_GAP_PX = 22;

type DashboardCachedState = {
  selectedProvider: string;
  hasIngestKey: boolean;
  hasEvents: boolean;
  setupStatusResolved: boolean;
  metrics: RealtimeMetrics | null;
  lastMetricsSuccessAt: string | null;
  protectDecisionStats: {
    allowed_60m: number | null;
    warned_60m: number | null;
    blocked_60m: number | null;
  } | null;
  incidents: IncidentItem[];
};

function buildInitialDashboardState(projectId: string | null | undefined): DashboardCachedState | null {
  return projectId ? readDashboardCache(projectId) : null;
}

function dashboardCacheKey(projectId: string): string {
  return `rheonic:dashboard:${projectId}`;
}

function readDashboardCache(projectId: string): DashboardCachedState | null {
  try {
    const raw = window.sessionStorage.getItem(dashboardCacheKey(projectId));
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<DashboardCachedState>;
    return {
      selectedProvider: typeof parsed.selectedProvider === "string" ? normalizeProviderValue(parsed.selectedProvider) || "all" : "all",
      hasIngestKey: Boolean(parsed.hasIngestKey),
      hasEvents: Boolean(parsed.hasEvents),
      setupStatusResolved: Boolean(parsed.setupStatusResolved),
      metrics: parsed.metrics ?? null,
      lastMetricsSuccessAt: parsed.lastMetricsSuccessAt ?? null,
      protectDecisionStats: parsed.protectDecisionStats ?? null,
      incidents: Array.isArray(parsed.incidents) ? parsed.incidents : [],
    };
  } catch {
    return null;
  }
}

function writeDashboardCache(projectId: string, state: DashboardCachedState): void {
  try {
    window.sessionStorage.setItem(dashboardCacheKey(projectId), JSON.stringify(state));
  } catch {
    // Ignore cache write failures and keep runtime state authoritative.
  }
}

function readDismissedFlag(storageKey: string): boolean {
  try {
    return window.localStorage.getItem(storageKey) === "1";
  } catch {
    return false;
  }
}

export function Dashboard(): JSX.Element {
  const { loadingProjects, projects, projectId } = useProjectContext();
  const navigate = useNavigate();
  const initialDashboardState = buildInitialDashboardState(projectId);

  const [metrics, setMetrics] = useState<RealtimeMetrics | null>(initialDashboardState?.metrics ?? null);
  const [incidents, setIncidents] = useState<IncidentItem[]>(initialDashboardState?.incidents ?? []);
  const [requestsSeries, setRequestsSeries] = useState<number[]>([]);
  const [tokensSeries, setTokensSeries] = useState<number[]>([]);
  const [loadingMetrics, setLoadingMetrics] = useState<boolean>(false);
  const [metricsWarning, setMetricsWarning] = useState<string | null>(null);
  const [lastMetricsSuccessAt, setLastMetricsSuccessAt] = useState<string | null>(initialDashboardState?.lastMetricsSuccessAt ?? null);
  const [lastIncidentsSuccessAt, setLastIncidentsSuccessAt] = useState<string | null>(null);
  const [lastProtectHealthSuccessAt, setLastProtectHealthSuccessAt] = useState<string | null>(null);
  const [metricsFetchFailed, setMetricsFetchFailed] = useState<boolean>(false);
  const [protectHealthFetchFailed, setProtectHealthFetchFailed] = useState<boolean>(false);
  const [protectHealth, setProtectHealth] = useState<ProtectHealthMetrics | null>(null);
  const [protectDecisionStats, setProtectDecisionStats] = useState<{
    allowed_60m: number | null;
    warned_60m: number | null;
    blocked_60m: number | null;
  } | null>(initialDashboardState?.protectDecisionStats ?? null);
  const [globalBanner, setGlobalBanner] = useState<string | null>(null);
  const [providers, setProviders] = useState<string[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>(initialDashboardState?.selectedProvider ?? "all");
  const providerRequestSeq = useRef<number>(0);
  const metricsRequestSeq = useRef<number>(0);
  const seriesByScopeRef = useRef<Record<string, { requests: number[]; tokens: number[] }>>({});
  const [hasIngestKey, setHasIngestKey] = useState<boolean>(initialDashboardState?.hasIngestKey ?? false);
  const [hasEvents, setHasEvents] = useState<boolean>(initialDashboardState?.hasEvents ?? false);
  const [setupStatusResolved, setSetupStatusResolved] = useState<boolean>(initialDashboardState?.setupStatusResolved ?? false);
  const [setupBannerDismissed, setSetupBannerDismissed] = useState<boolean>(() => readDismissedFlag(`rheonic:setupBannerDismissed:${projectId ?? "none"}`));
  const [webhookIssue, setWebhookIssue] = useState<{ count: number; lastAt: string | null } | null>(null);
  const [webhookIssueDismissedToken, setWebhookIssueDismissedToken] = useState<string | null>(null);
  const [setupBannerClosing, setSetupBannerClosing] = useState<boolean>(false);
  const [webhookIssueBannerClosing, setWebhookIssueBannerClosing] = useState<boolean>(false);
  const [bannerOverlayStyle, setBannerOverlayStyle] = useState<{ top: number; right: number; width: number }>({
    top: 120,
    right: 24,
    width: 420,
  });
  const dashboardContentRef = useRef<HTMLDivElement | null>(null);
  const heroDividerRef = useRef<HTMLDivElement | null>(null);
  const tokenCardSlotClassName = "dashboard-banner-target";

  const setupDismissStorageKey = useMemo<string>(() => `rheonic:setupBannerDismissed:${projectId ?? "none"}`, [projectId]);
  const webhookIssueDismissStorageKey = useMemo<string>(() => `rheonic:webhookIssueDismissed:${projectId ?? "none"}`, [projectId]);
  const setupStage = useMemo<SetupStage>(() => {
    if (loadingProjects) {
      return "checking";
    }
    if (projects.length === 0) {
      return "no_project";
    }
    if (!projectId) {
      return "no_selection";
    }
    if (!setupStatusResolved) {
      return "checking";
    }
    if (!hasIngestKey) {
      return "no_ingest_key";
    }
    if (!hasEvents) {
      return "no_events";
    }
    return "complete";
  }, [hasEvents, hasIngestKey, loadingProjects, projectId, projects.length, setupStatusResolved]);
  const isSetupComplete = setupStage === "complete";
  const showSetupBanner = !loadingProjects && setupStage !== "complete" && setupStage !== "checking" && !setupBannerDismissed;
  const webhookIssueToken = webhookIssue ? `${webhookIssue.lastAt ?? "none"}:${webhookIssue.count}` : null;
  const showWebhookIssueBanner = Boolean(projectId && webhookIssue && webhookIssueToken !== webhookIssueDismissedToken);
  const renderSetupBanner = showSetupBanner || setupBannerClosing;
  const renderWebhookIssueBanner = showWebhookIssueBanner || webhookIssueBannerClosing;

  const incidentSummary = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const incident of incidents) {
      counts[incident.type] = (counts[incident.type] ?? 0) + 1;
    }
    return counts;
  }, [incidents]);

  useLayoutEffect(() => {
    const cached = projectId ? readDashboardCache(projectId) : null;
    setMetrics(cached?.metrics ?? null);
    setIncidents(cached?.incidents ?? []);
    setRequestsSeries([]);
    setTokensSeries([]);
    seriesByScopeRef.current = {};
    setMetricsWarning(null);
    setGlobalBanner(null);
    setProtectDecisionStats(cached?.protectDecisionStats ?? null);
    setProtectHealth(null);
    setLastProtectHealthSuccessAt(null);
    setProtectHealthFetchFailed(false);
    setProviders([]);
    setSelectedProvider(cached?.selectedProvider ?? "all");
    setHasIngestKey(cached?.hasIngestKey ?? false);
    setHasEvents(cached?.hasEvents ?? false);
    setSetupStatusResolved(cached?.setupStatusResolved ?? false);
    setWebhookIssue(null);
    setWebhookIssueDismissedToken(null);
    setSetupBannerClosing(false);
    setWebhookIssueBannerClosing(false);
    setLastMetricsSuccessAt(cached?.lastMetricsSuccessAt ?? null);
  }, [projectId]);

  useEffect(() => {
    if (!projectId) {
      return;
    }
    // Persist the last successful dashboard snapshot so revisiting the page does not flash onboarding state.
    writeDashboardCache(projectId, {
      selectedProvider,
      hasIngestKey,
      hasEvents,
      setupStatusResolved,
      metrics,
      lastMetricsSuccessAt,
      protectDecisionStats,
      incidents,
    });
  }, [hasEvents, hasIngestKey, incidents, lastMetricsSuccessAt, metrics, projectId, protectDecisionStats, selectedProvider, setupStatusResolved]);

  useEffect(() => {
    setSetupBannerDismissed(readDismissedFlag(setupDismissStorageKey));
  }, [setupDismissStorageKey]);

  useEffect(() => {
    const dismissed = window.localStorage.getItem(webhookIssueDismissStorageKey);
    setWebhookIssueDismissedToken(dismissed);
  }, [webhookIssueDismissStorageKey]);

  useEffect(() => {
    if (setupStage !== "complete") {
      return;
    }
    window.localStorage.removeItem(setupDismissStorageKey);
    setSetupBannerDismissed(false);
  }, [setupDismissStorageKey, setupStage]);

  useEffect(() => {
    if (loadingProjects) {
      return;
    }
    if (!projectId) {
      setHasIngestKey(false);
      setHasEvents(false);
      setSetupStatusResolved(true);
      return;
    }

    let cancelled = false;
    const loadSetupSignals = async (): Promise<void> => {
      let setupSignalsLoaded = false;
      try {
        const [keys, projectProviders] = await Promise.all([listKeys(projectId), fetchProjectProviders(projectId)]);
        if (cancelled) {
          return;
        }
        setupSignalsLoaded = true;
        setHasIngestKey(keys.some((key) => key.status === "active"));
        setHasEvents(projectProviders.length > 0);
      } catch {
        if (cancelled) {
          return;
        }
        // Keep the last known setup state during transient backend outages.
      } finally {
        if (!cancelled && setupSignalsLoaded) {
          setSetupStatusResolved(true);
        }
      }
    };

    void loadSetupSignals();
    const interval = window.setInterval(() => {
      void loadSetupSignals();
    }, 5_000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [loadingProjects, projectId]);

  const dismissSetupBanner = useCallback((): void => {
    setSetupBannerClosing(true);
    window.setTimeout(() => {
      window.localStorage.setItem(setupDismissStorageKey, "1");
      setSetupBannerDismissed(true);
      setSetupBannerClosing(false);
    }, DASHBOARD_BANNER_EXIT_MS);
  }, [setupDismissStorageKey]);

  const dismissWebhookIssueBanner = useCallback((): void => {
    if (!webhookIssueToken) {
      return;
    }
    setWebhookIssueBannerClosing(true);
    window.setTimeout(() => {
      window.localStorage.setItem(webhookIssueDismissStorageKey, webhookIssueToken);
      setWebhookIssueDismissedToken(webhookIssueToken);
      setWebhookIssueBannerClosing(false);
    }, DASHBOARD_BANNER_EXIT_MS);
  }, [webhookIssueDismissStorageKey, webhookIssueToken]);

  useLayoutEffect(() => {
    const content = dashboardContentRef.current;
    const divider = heroDividerRef.current;
    if (!content || !divider) {
      return;
    }

    const updateBannerOverlayTop = (): void => {
      const contentRect = content.getBoundingClientRect();
      const dividerRect = divider.getBoundingClientRect();
      const tokenCard = content.querySelector<HTMLElement>(`.${tokenCardSlotClassName}`);
      const tokenCardRect = tokenCard?.getBoundingClientRect() ?? null;
      const nextTop = Math.max(12, dividerRect.bottom - 2);
      const nextRight = Math.max(14, tokenCardRect ? window.innerWidth - tokenCardRect.right : window.innerWidth - contentRect.right);
      const nextWidth = Math.max(320, tokenCardRect ? tokenCardRect.width : (contentRect.width - DASHBOARD_METRICS_GAP_PX) / 2);
      setBannerOverlayStyle({ top: nextTop, right: nextRight, width: nextWidth });
    };

    updateBannerOverlayTop();
    const resizeObserver = new ResizeObserver(() => {
      updateBannerOverlayTop();
    });
    resizeObserver.observe(content);
    resizeObserver.observe(divider);
    window.addEventListener("resize", updateBannerOverlayTop);
    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", updateBannerOverlayTop);
    };
  }, [projectId]);

  const setupBannerContent = useMemo<{
    title: string;
    text: string;
    primaryLabel?: string;
    primaryTo?: string;
    secondaryLabel?: string;
    secondaryTo?: string;
  }>(() => {
    if (setupStage === "no_project") {
      return {
        title: "Setup required",
        text: "Create your first project to generate an ingest key and follow next steps in Quickstart.",
        primaryLabel: "Go to Projects",
        primaryTo: "/app/projects",
        secondaryLabel: "Open Quickstart",
        secondaryTo: "/quickstart",
      };
    }
    if (setupStage === "no_selection") {
      return {
        title: "Setup required",
        text: "Select a project to view metrics. Then create an ingest key and instrument your provider.",
        primaryLabel: "Open Projects",
        primaryTo: "/app/projects",
        secondaryLabel: "Open Quickstart",
        secondaryTo: "/quickstart",
      };
    }
    if (setupStage === "no_ingest_key") {
      return {
        title: "Setup required",
        text: "Create an ingest key to start receiving telemetry and preflight decisions.",
        primaryLabel: "Open Keys",
        primaryTo: "/app/keys",
        secondaryLabel: "Open Quickstart",
        secondaryTo: "/quickstart",
      };
    }
    if (setupStage === "no_events") {
      return {
        title: "Setup required",
        text: "Waiting for first event. Run one instrumented provider call to verify integration.",
        primaryLabel: "Open Quickstart",
        primaryTo: "/quickstart",
      };
    }
    return {
      title: "Setup required",
      text: "Checking setup status for this project.",
      secondaryLabel: "Open Quickstart",
      secondaryTo: "/quickstart",
    };
  }, [setupStage]);

  const refreshProviders = useCallback(async (): Promise<void> => {
    if (!projectId) {
      return;
    }
    providerRequestSeq.current += 1;
    const requestSeq = providerRequestSeq.current;
    try {
      const items = await fetchProjectProviders(projectId);
      if (requestSeq !== providerRequestSeq.current) {
        return;
      }
      const normalized = Array.from(new Set(items.map((provider) => normalizeProviderValue(provider)).filter(Boolean)));
      setProviders(normalized);
      setSelectedProvider((current) => (current !== "all" && !normalized.includes(normalizeProviderValue(current)) ? "all" : current));
    } catch {
      if (requestSeq !== providerRequestSeq.current) {
        return;
      }
      setProviders([]);
      setSelectedProvider("all");
    }
  }, [projectId]);

  useEffect(() => {
    void refreshProviders();
  }, [refreshProviders]);

  useEffect(() => {
    if (!projectId) {
      return;
    }

    let cancelled = false;
    const providerQuery = selectedProvider === "all" ? undefined : selectedProvider;
    const loadProtectStats = async (): Promise<void> => {
      try {
        const data = await fetchProtectMetrics(projectId, providerQuery);
        if (cancelled) {
          return;
        }
        setProtectDecisionStats({
          allowed_60m: data.allowed_60m,
          warned_60m: data.warned_60m,
          blocked_60m: data.blocked_60m,
        });
      } catch {
        if (!cancelled) {
          setProtectDecisionStats(null);
        }
      }
    };

    void loadProtectStats();
    const interval = window.setInterval(() => {
      void loadProtectStats();
    }, frontendConfig.dashboardProtectStatsPollMs);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [projectId, selectedProvider, providers]);

  useEffect(() => {
    if (!projectId) {
      return;
    }

    let cancelled = false;
    const providerQuery = selectedProvider === "all" ? undefined : selectedProvider;

    const loadProtectHealth = async (): Promise<void> => {
      try {
        const data = await fetchProtectHealth(projectId, providerQuery);
        if (cancelled) {
          return;
        }
        setProtectHealth(data);
        setProtectHealthFetchFailed(false);
        setLastProtectHealthSuccessAt(new Date().toISOString());
      } catch {
        if (!cancelled) {
          setProtectHealthFetchFailed(true);
          setProtectHealth(null);
        }
      }
    };

    void loadProtectHealth();
    const interval = window.setInterval(() => {
      void loadProtectHealth();
    }, frontendConfig.dashboardProtectStatsPollMs);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [projectId, selectedProvider]);

  useEffect(() => {
    if (!projectId) {
      setLoadingMetrics(false);
      return;
    }

    let cancelled = false;
    metricsRequestSeq.current += 1;
    const requestSeq = metricsRequestSeq.current;
    setLoadingMetrics(true);
    const scopeKey = `${projectId}:${selectedProvider}`;
    const cachedSeries = seriesByScopeRef.current[scopeKey];
    setRequestsSeries(cachedSeries?.requests ?? []);
    setTokensSeries(cachedSeries?.tokens ?? []);
    const providerQuery = selectedProvider === "all" ? undefined : selectedProvider;
    const providerKeys = providers.filter((provider) => provider !== "all");

    const loadMetrics = async (): Promise<void> => {
      try {
        const data =
          selectedProvider === "all" && providerKeys.length > 0
            ? await fetchAggregatedMetrics(projectId, providerKeys)
            : await fetchMetrics(projectId, providerQuery);
        if (cancelled || requestSeq !== metricsRequestSeq.current) {
          return;
        }

        setMetrics(data);
        setMetricsWarning(null);
        setGlobalBanner(null);
        setMetricsFetchFailed(false);
        setLastMetricsSuccessAt(new Date().toISOString());
        const currentSeries = seriesByScopeRef.current[scopeKey] ?? { requests: [], tokens: [] };
        const nextRequests = [...currentSeries.requests.slice(-(frontendConfig.dashboardMaxSeriesPoints - 1)), data.requests_60s];
        const nextTokens = [...currentSeries.tokens.slice(-(frontendConfig.dashboardMaxSeriesPoints - 1)), data.tokens_60s];
        seriesByScopeRef.current[scopeKey] = {
          requests: nextRequests,
          tokens: nextTokens,
        };
        setRequestsSeries(nextRequests);
        setTokensSeries(nextTokens);
      } catch (error) {
        if (!cancelled && requestSeq === metricsRequestSeq.current) {
          if (error instanceof ApiError && error.status === 403) {
            setGlobalBanner("You do not have access to this project's metrics.");
            setMetricsWarning("Metrics request was forbidden.");
          } else {
            setMetricsWarning("Metrics polling failed.");
          }
          setMetricsFetchFailed(true);
        }
      } finally {
        if (!cancelled && requestSeq === metricsRequestSeq.current) {
          setLoadingMetrics(false);
        }
      }
    };

    void loadMetrics();
    const interval = window.setInterval(() => {
      void loadMetrics();
    }, frontendConfig.dashboardMetricsPollMs);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [projectId, selectedProvider, providers]);

  async function fetchAggregatedMetrics(project: string, providersList: string[]): Promise<RealtimeMetrics> {
    const rows = await Promise.all(providersList.map(async (provider) => ({ provider, metrics: await fetchMetrics(project, provider) })));
    let totalReq = 0;
    let totalTok = 0;
    for (const row of rows) {
      const providerScopeKey = `${project}:${row.provider}`;
      const providerSeries = seriesByScopeRef.current[providerScopeKey] ?? { requests: [], tokens: [] };
      const providerNextRequests = [...providerSeries.requests.slice(-(frontendConfig.dashboardMaxSeriesPoints - 1)), row.metrics.requests_60s];
      const providerNextTokens = [...providerSeries.tokens.slice(-(frontendConfig.dashboardMaxSeriesPoints - 1)), row.metrics.tokens_60s];
      seriesByScopeRef.current[providerScopeKey] = {
        requests: providerNextRequests,
        tokens: providerNextTokens,
      };
      totalReq += row.metrics.requests_60s;
      totalTok += row.metrics.tokens_60s;
    }
    return {
      requests_60s: totalReq,
      tokens_60s: totalTok,
    };
  }

  useEffect(() => {
    if (!projectId) {
      return;
    }

    let cancelled = false;
    const providerQuery = selectedProvider === "all" ? undefined : selectedProvider;

    const loadIncidents = async (): Promise<void> => {
      try {
        const data = await fetchIncidents(projectId, providerQuery);
        if (cancelled) {
          return;
        }

        setIncidents(data);
        setGlobalBanner(null);
        setLastIncidentsSuccessAt(new Date().toISOString());
      } catch (error) {
        if (!cancelled) {
          if (error instanceof ApiError && error.status === 403) {
            setGlobalBanner("You do not have access to this project's incidents.");
          }
        }
      }
    };

    void loadIncidents();
    const interval = window.setInterval(() => {
      void loadIncidents();
    }, frontendConfig.dashboardIncidentsPollMs);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [projectId, selectedProvider]);

  useEffect(() => {
    if (!projectId) {
      setWebhookIssue(null);
      return;
    }

    let cancelled = false;
    const loadWebhookIssue = async (): Promise<void> => {
      try {
        const issue = await fetchDeliveryFailures(projectId, "webhook");
        if (cancelled) {
          return;
        }
        setWebhookIssue(issue.count > 0 ? { count: issue.count, lastAt: issue.last_attempt_at } : null);
      } catch {
        if (!cancelled) {
          setWebhookIssue(null);
        }
      }
    };

    void loadWebhookIssue();
    const interval = window.setInterval(() => {
      void loadWebhookIssue();
    }, 15_000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [projectId]);

  const renderMetric = (value: number | null | undefined): string => (value === null || value === undefined ? "—" : String(value));
  const protectStatus = useMemo<{
    label: string;
    tone: ProtectStatus;
  }>(() => {
    if (!projectId || setupStage !== "complete") {
      return {
        label: "Awaiting traffic",
        tone: "awaiting",
      };
    }
    if (
      protectHealthFetchFailed ||
      !lastProtectHealthSuccessAt ||
      Date.now() - new Date(lastProtectHealthSuccessAt).getTime() > frontendConfig.dashboardProtectStatsPollMs * 2
    ) {
      return {
        label: "Unavailable",
        tone: "unavailable",
      };
    }
    if ((protectHealth?.timeouts_30m ?? 0) > 3) {
      return {
        label: "Degraded",
        tone: "degraded",
      };
    }
    if ((protectHealth?.p95_ms ?? 0) >= 250) {
      return {
        label: "Degraded",
        tone: "degraded",
      };
    }
    return {
      label: "Healthy",
      tone: "healthy",
    };
  }, [lastProtectHealthSuccessAt, projectId, protectHealth, protectHealthFetchFailed, setupStage]);

  return (
    <main className="dashboard">
      <div className="dashboard-content" ref={dashboardContentRef}>
        {(globalBanner || renderSetupBanner || renderWebhookIssueBanner) ? (
          <section
            className="dashboard-banner-overlay"
            style={{
              top: `${bannerOverlayStyle.top}px`,
              right: `${bannerOverlayStyle.right}px`,
              width: `${bannerOverlayStyle.width}px`,
            }}
            aria-live="polite"
          >
            <div className="dashboard-banner-rail">
              {globalBanner ? <section className="banner dashboard-floating-banner">{globalBanner}</section> : null}
              {renderSetupBanner ? (
                <section className={`setup-banner dashboard-floating-banner${setupBannerClosing ? " dashboard-floating-banner--closing" : ""}`}>
                  <div className="dashboard-alert-banner-layout">
                    <div className="setup-banner-title dashboard-alert-banner-title">{setupBannerContent.title}</div>
                    <div className="setup-banner-text dashboard-alert-banner-summary">{setupBannerContent.text}</div>
                    <div className="setup-banner-actions dashboard-alert-banner-actions">
                    {setupBannerContent.primaryLabel && setupBannerContent.primaryTo ? (
                      <button type="button" className="modal-button modal-primary" onClick={() => navigate(setupBannerContent.primaryTo)}>
                        {setupBannerContent.primaryLabel}
                      </button>
                    ) : null}
                    {setupBannerContent.secondaryLabel && setupBannerContent.secondaryTo ? (
                      <button type="button" className="modal-button" onClick={() => navigate(setupBannerContent.secondaryTo)}>
                        {setupBannerContent.secondaryLabel}
                      </button>
                    ) : null}
                    <button type="button" className="modal-button" onClick={dismissSetupBanner}>
                      Dismiss
                    </button>
                    </div>
                  </div>
                </section>
              ) : null}
              {renderWebhookIssueBanner ? (
                <section className={`dashboard-alert-card dashboard-floating-banner${webhookIssueBannerClosing ? " dashboard-floating-banner--closing" : ""}`}>
                  <div className="dashboard-alert-banner-layout">
                    <h2 className="card-title dashboard-alert-banner-title">Webhook delivery issues in the last 24 hours</h2>
                    <p className="subtle dashboard-alert-banner-summary">
                      {webhookIssue.count} {webhookIssue.count === 1 ? "delivery failed" : "deliveries failed"}
                      {webhookIssue.lastAt ? ` • Last attempt ${formatAlertAttemptTime(webhookIssue.lastAt)}` : ""}
                    </p>
                    <div className="modal-actions form-actions dashboard-alert-banner-actions">
                      <button type="button" className="modal-button modal-primary" onClick={() => navigate("/app/alerts")}>
                        Check URL
                      </button>
                      <button type="button" className="modal-button" onClick={dismissWebhookIssueBanner}>
                        Dismiss
                      </button>
                    </div>
                  </div>
                </section>
              ) : null}
            </div>
          </section>
        ) : null}
        <section className="dashboard-hero">
          <div className="dashboard-hero-left">
            <h1 className="page-title">LLM Control Center</h1>
            <p className="page-subtitle">Real-time monitoring and protection</p>
            <div ref={heroDividerRef} className="hero-subtitle-divider" aria-hidden="true" />
          </div>
          <div className="dashboard-hero-right">
            <div className="status-panel status-panel--accent" aria-live="polite">
              <div className="status-row">
                <span className="status-row-label">System status</span>
                <span className={`status-row-value status-${protectStatus.tone}`}>
                  {protectStatus.label}
                </span>
              </div>
              <div className="status-row">
                <span className="status-row-label">Dashboard sync</span>
                <span className="status-row-value time-value">{formatTime(lastMetricsSuccessAt)}</span>
              </div>
            </div>
          </div>
        </section>

        {!projectId ? (
          showSetupBanner ? null : (
            <section className="empty">
              <p>Select a project to see realtime metrics.</p>
            </section>
          )
        ) : (
          <>
            <section className="dashboard-controls-main">
              <div className="toolbar">
                <label htmlFor="dashboard-provider-select">Provider</label>
                <select
                  id="dashboard-provider-select"
                  value={selectedProvider}
                  onChange={(event) => {
                    setSelectedProvider(normalizeProviderValue(event.target.value));
                    event.currentTarget.blur();
                  }}
                  onFocus={() => {
                    void refreshProviders();
                  }}
                  onMouseDown={() => {
                    void refreshProviders();
                  }}
                  onTouchStart={() => {
                    void refreshProviders();
                  }}
                >
                  <option value="all">All</option>
                  {providers.map((provider) => (
                    <option key={provider} value={provider}>
                      {formatProviderLabel(provider)}
                    </option>
                  ))}
                </select>
              </div>
            </section>
            <section className="metrics-grid">
              <Card>
                <h2 className="card-title">Requests (60s)</h2>
                <p className="metric-value">{loadingMetrics && !metrics ? "..." : formatNumber(metrics?.requests_60s ?? 0)}</p>
                <PulseMeter
                  values={requestsSeries}
                  color="var(--req)"
                  mode="requests"
                />
                <div className="metric-card-bottom-spacer" aria-hidden="true" />
              </Card>

              <Card className={tokenCardSlotClassName}>
                <h2 className="card-title">Tokens (60s)</h2>
                <p className="metric-value">{loadingMetrics && !metrics ? "..." : formatNumber(metrics?.tokens_60s ?? 0)}</p>
                <PulseMeter
                  values={tokensSeries}
                  color="var(--accent)"
                  mode="tokens"
                />
                <div className="metric-card-bottom-spacer" aria-hidden="true" />
              </Card>

              <Card>
                <h2 className="card-title">Incidents</h2>
                <div className="protect-decisions-list">
                  <div className="protect-decisions-row">
                    <span className="protect-decisions-label">Near cap</span>
                    <span className="protect-decisions-value warned">{incidentSummary.near_cap ?? 0}</span>
                  </div>
                  <div className="protect-decisions-row">
                    <span className="protect-decisions-label">Retry storm</span>
                    <span className="protect-decisions-value warned">{incidentSummary.retry_storm ?? 0}</span>
                  </div>
                  <div className="protect-decisions-row">
                    <span className="protect-decisions-label">Loop suspect</span>
                    <span className="protect-decisions-value warned">{incidentSummary.loop_suspect ?? 0}</span>
                  </div>
                  <div className="protect-decisions-row">
                    <span className="protect-decisions-label">Token explosion</span>
                    <span className="protect-decisions-value warned">{incidentSummary.token_explosion ?? 0}</span>
                  </div>
                  <div className="protect-decisions-row">
                    <span className="protect-decisions-label">Cap breach</span>
                    <span className="protect-decisions-value blocked">{incidentSummary.cap_breach ?? 0}</span>
                  </div>
                </div>
              </Card>

              <Card>
                <h2 className="card-title">Protect decisions (60m)</h2>
                <div className="protect-decisions-list">
                  <div className="protect-decisions-row">
                    <span className="protect-decisions-label">Allowed</span>
                    <span className="protect-decisions-value">{renderMetric(protectDecisionStats?.allowed_60m)}</span>
                  </div>
                  <div className="protect-decisions-row">
                    <span className="protect-decisions-label">Warned</span>
                    <span className="protect-decisions-value warned">{renderMetric(protectDecisionStats?.warned_60m)}</span>
                  </div>
                  <div className="protect-decisions-row">
                    <span className="protect-decisions-label">Blocked</span>
                    <span className="protect-decisions-value blocked">{renderMetric(protectDecisionStats?.blocked_60m)}</span>
                  </div>
                </div>
              </Card>
            </section>
          </>
        )}
        <p className="dashboard-beta-note">Rheonic is in beta — your feedback shapes the product!</p>
      </div>
    </main>
  );
}
