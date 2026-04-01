import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { formatNumber, formatTime } from "./dashboardUtils";
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
import { InfoTooltip } from "../components/InfoTooltip";
import { PulseMeter } from "../components/pulseMeter";
import { frontendConfig } from "../config";
import { useProjectContext } from "../context/ProjectContext";
import { mergeProjectWarmState, readProjectWarmState } from "../lib/projectWarmCache";

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

type DashboardCachedState = {
  selectedProvider: string;
  hasIngestKey: boolean;
  hasEvents: boolean;
  setupStatusResolved: boolean;
  metrics: RealtimeMetrics | null;
  lastMetricsSuccessAt: string | null;
  protectHealth: ProtectHealthMetrics | null;
  lastProtectHealthSuccessAt: string | null;
  protectDecisionStats: {
    allowed_60m: number | null;
    clamped_60m: number | null;
    blocked_60m: number | null;
  } | null;
};

const dashboardMemoryCache = new Map<string, DashboardCachedState>();

function buildInitialDashboardState(projectId: string | null | undefined): DashboardCachedState | null {
  if (!projectId) {
    return null;
  }
  const cached = readDashboardCache(projectId);
  if (cached) {
    return cached;
  }
  const warm = readProjectWarmState(projectId);
  if (!warm) {
    return null;
  }
  const setupSignalsResolved = typeof warm.hasIngestKey === "boolean" && Array.isArray(warm.providers);
  return {
    selectedProvider: "all",
    hasIngestKey: warm.hasIngestKey ?? false,
    hasEvents: (warm.providers?.length ?? 0) > 0,
    setupStatusResolved: setupSignalsResolved,
    metrics: null,
    lastMetricsSuccessAt: null,
    protectHealth: warm.protectHealth ?? null,
    lastProtectHealthSuccessAt: warm.lastProtectHealthSuccessAt ?? null,
    protectDecisionStats: warm.protectDecisionStats ?? null,
  };
}

function readDashboardCache(projectId: string): DashboardCachedState | null {
  return dashboardMemoryCache.get(projectId) ?? null;
}

function writeDashboardCache(projectId: string, state: DashboardCachedState): void {
  dashboardMemoryCache.set(projectId, state);
}

export function Dashboard(): JSX.Element {
  const { loadingProjects, projects, projectId } = useProjectContext();
  const navigate = useNavigate();
  const initialDashboardState = buildInitialDashboardState(projectId);
  const initialWarmState = readProjectWarmState(projectId);

  const [metrics, setMetrics] = useState<RealtimeMetrics | null>(initialDashboardState?.metrics ?? null);
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [requestsSeries, setRequestsSeries] = useState<number[]>([]);
  const [tokensSeries, setTokensSeries] = useState<number[]>([]);
  const [loadingMetrics, setLoadingMetrics] = useState<boolean>(false);
  const [, setMetricsWarning] = useState<string | null>(null);
  const [lastMetricsSuccessAt, setLastMetricsSuccessAt] = useState<string | null>(initialDashboardState?.lastMetricsSuccessAt ?? null);
  const [, setLastIncidentsSuccessAt] = useState<string | null>(null);
  const [lastProtectHealthSuccessAt, setLastProtectHealthSuccessAt] = useState<string | null>(initialDashboardState?.lastProtectHealthSuccessAt ?? null);
  const [, setMetricsFetchFailed] = useState<boolean>(false);
  const [protectHealthFetchFailed, setProtectHealthFetchFailed] = useState<boolean>(false);
  const [protectHealthResolved, setProtectHealthResolved] = useState<boolean>(
    Boolean(initialDashboardState?.lastProtectHealthSuccessAt),
  );
  const [protectHealth, setProtectHealth] = useState<ProtectHealthMetrics | null>(initialDashboardState?.protectHealth ?? null);
  const [protectDecisionStats, setProtectDecisionStats] = useState<{
    allowed_60m: number | null;
    clamped_60m: number | null;
    blocked_60m: number | null;
  } | null>(initialDashboardState?.protectDecisionStats ?? null);
  const [globalBanner, setGlobalBanner] = useState<string | null>(null);
  const [providers, setProviders] = useState<string[]>(initialWarmState?.providers ?? []);
  const [selectedProvider, setSelectedProvider] = useState<string>(initialDashboardState?.selectedProvider ?? "all");
  const providerRequestSeq = useRef<number>(0);
  const metricsRequestSeq = useRef<number>(0);
  const lastProtectHealthSuccessAtRef = useRef<string | null>(initialDashboardState?.lastProtectHealthSuccessAt ?? null);
  const activeMetricsScopeRef = useRef<string | null>(null);
  const seriesByScopeRef = useRef<Record<string, { requests: number[]; tokens: number[] }>>({});
  const [hasIngestKey, setHasIngestKey] = useState<boolean>(initialDashboardState?.hasIngestKey ?? false);
  const [hasEvents, setHasEvents] = useState<boolean>(initialDashboardState?.hasEvents ?? false);
  const [setupStatusResolved, setSetupStatusResolved] = useState<boolean>(initialDashboardState?.setupStatusResolved ?? false);
  const [setupBannerDismissed, setSetupBannerDismissed] = useState<boolean>(false);
  const [webhookIssue, setWebhookIssue] = useState<{ count: number; lastAt: string | null } | null>(null);
  const [webhookIssueDismissedToken, setWebhookIssueDismissedToken] = useState<string | null>(null);
  const [setupBannerClosing, setSetupBannerClosing] = useState<boolean>(false);
  const [webhookIssueBannerClosing, setWebhookIssueBannerClosing] = useState<boolean>(false);

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
  const showSetupBanner = !loadingProjects && setupStage !== "complete" && setupStage !== "checking" && !setupBannerDismissed;
  const webhookIssueToken = webhookIssue ? `${webhookIssue.lastAt ?? "none"}:${webhookIssue.count}` : null;
  const showWebhookIssueBanner = Boolean(projectId && webhookIssue && webhookIssueToken !== webhookIssueDismissedToken);
  const renderSetupBanner = showSetupBanner || setupBannerClosing;
  const renderWebhookIssueBanner = showWebhookIssueBanner || webhookIssueBannerClosing;
  const hideDashboardHero = !projectId;
  const useFullWidthSetupBanner = renderSetupBanner && !globalBanner && !renderWebhookIssueBanner;

  const incidentSummary = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const incident of incidents) {
      counts[incident.type] = (counts[incident.type] ?? 0) + 1;
    }
    return counts;
  }, [incidents]);

  const applyProviders = useCallback((items: string[]): void => {
    const normalized = Array.from(new Set(items.map((provider) => normalizeProviderValue(provider)).filter(Boolean)));
    setProviders(normalized);
    setSelectedProvider((current) => (current !== "all" && !normalized.includes(normalizeProviderValue(current)) ? "all" : current));
  }, []);

  useLayoutEffect(() => {
    const cached = projectId ? readDashboardCache(projectId) : null;
    const warm = readProjectWarmState(projectId);
    setMetrics(cached?.metrics ?? null);
    setIncidents([]);
    setRequestsSeries([]);
    setTokensSeries([]);
    seriesByScopeRef.current = {};
    setMetricsWarning(null);
    setGlobalBanner(null);
    setProtectDecisionStats(cached?.protectDecisionStats ?? null);
    setProtectHealth(cached?.protectHealth ?? null);
    setLastProtectHealthSuccessAt(cached?.lastProtectHealthSuccessAt ?? null);
    setProtectHealthFetchFailed(false);
    setProtectHealthResolved(Boolean(cached?.lastProtectHealthSuccessAt));
    setProviders(warm?.providers ?? []);
    setSelectedProvider(cached?.selectedProvider ?? "all");
    setHasIngestKey(cached?.hasIngestKey ?? warm?.hasIngestKey ?? false);
    setHasEvents(cached?.hasEvents ?? ((warm?.providers?.length ?? 0) > 0));
    setSetupStatusResolved(cached?.setupStatusResolved ?? (typeof warm?.hasIngestKey === "boolean" && Array.isArray(warm?.providers)));
    setWebhookIssue(null);
    setWebhookIssueDismissedToken(null);
    setSetupBannerClosing(false);
    setWebhookIssueBannerClosing(false);
    setLastMetricsSuccessAt(cached?.lastMetricsSuccessAt ?? null);
  }, [projectId]);

  useEffect(() => {
    lastProtectHealthSuccessAtRef.current = lastProtectHealthSuccessAt;
  }, [lastProtectHealthSuccessAt]);

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
      protectHealth,
      lastProtectHealthSuccessAt,
      protectDecisionStats,
    });
  }, [hasEvents, hasIngestKey, lastMetricsSuccessAt, lastProtectHealthSuccessAt, metrics, projectId, protectDecisionStats, protectHealth, selectedProvider, setupStatusResolved]);

  useEffect(() => {
    const dismissed = window.localStorage.getItem(webhookIssueDismissStorageKey);
    setWebhookIssueDismissedToken(dismissed);
  }, [webhookIssueDismissStorageKey]);

  useEffect(() => {
    if (setupStage !== "complete") {
      return undefined;
    }
    setSetupBannerDismissed(false);
    return undefined;
  }, [setupStage]);

  useEffect(() => {
    if (loadingProjects) {
      return undefined;
    }
    if (!projectId) {
      setHasIngestKey(false);
      setHasEvents(false);
      setSetupStatusResolved(true);
      return undefined;
    }

    let cancelled = false;
    const loadSetupSignals = async (): Promise<void> => {
      const [keysResult, providersResult] = await Promise.allSettled([
        listKeys(projectId),
        fetchProjectProviders(projectId),
      ]);
      if (cancelled) {
        return;
      }

      let setupSignalsLoaded = false;
      if (keysResult.status === "fulfilled") {
        setHasIngestKey(keysResult.value.some((key) => key.status === "active"));
        setupSignalsLoaded = true;
      }
      if (providersResult.status === "fulfilled") {
        setHasEvents(providersResult.value.length > 0);
        applyProviders(providersResult.value);
        setupSignalsLoaded = true;
      }
      if (setupSignalsLoaded) {
        setSetupStatusResolved(true);
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
  }, [applyProviders, loadingProjects, projectId]);

  const dismissSetupBanner = useCallback((): void => {
    setSetupBannerClosing(true);
    window.setTimeout(() => {
      setSetupBannerDismissed(true);
      setSetupBannerClosing(false);
    }, DASHBOARD_BANNER_EXIT_MS);
  }, []);

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

  const setupBannerContent = useMemo<{
    title: string;
    text: JSX.Element | string;
    primaryLabel?: string;
    primaryTo?: string;
    secondaryLabel?: string;
    secondaryTo?: string;
  }>(() => {
    if (setupStage === "no_project") {
      return {
        title: "Setup required",
        text: (
          <>
            Create your first project.
            <br />
            Generate an ingest key, then follow Quickstart.
          </>
        ),
        primaryLabel: "Projects",
        primaryTo: "/app/projects",
        secondaryLabel: "Quickstart",
        secondaryTo: "/quickstart",
      };
    }
    if (setupStage === "no_selection") {
      return {
        title: "Setup required",
        text: "Select a project, generate an ingest key, then follow Quickstart.",
        primaryLabel: "Projects",
        primaryTo: "/app/projects",
        secondaryLabel: "Quickstart",
        secondaryTo: "/quickstart",
      };
    }
    if (setupStage === "no_ingest_key") {
      return {
        title: "Setup required",
        text: (
          <>
            Generate an ingest key.
            <br />
            Then follow Quickstart to instrument your SDK.
          </>
        ),
        primaryLabel: "Keys",
        primaryTo: "/app/keys",
        secondaryLabel: "Quickstart",
        secondaryTo: "/quickstart",
      };
    }
    if (setupStage === "no_events") {
      return {
        title: "Setup required",
        text: (
          <>
            Waiting for first event.
            <br />
            Run one instrumented provider call to verify integration.
          </>
        ),
        primaryLabel: "Quickstart",
        primaryTo: "/quickstart",
      };
    }
    return {
      title: "Setup required",
      text: "Checking setup status for this project.",
      secondaryLabel: "Quickstart",
      secondaryTo: "/quickstart",
    };
  }, [setupStage]);
  const setupPrimaryTarget = setupBannerContent.primaryLabel && setupBannerContent.primaryTo
    ? { label: setupBannerContent.primaryLabel, to: setupBannerContent.primaryTo }
    : null;
  const setupSecondaryTarget = setupBannerContent.secondaryLabel && setupBannerContent.secondaryTo
    ? { label: setupBannerContent.secondaryLabel, to: setupBannerContent.secondaryTo }
    : null;
  const visibleWebhookIssue = renderWebhookIssueBanner && webhookIssue ? webhookIssue : null;

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
      applyProviders(items);
    } catch {
      if (requestSeq !== providerRequestSeq.current) {
        return;
      }
      setProviders([]);
      setSelectedProvider("all");
    }
  }, [applyProviders, projectId]);

  useEffect(() => {
    void refreshProviders();
  }, [refreshProviders]);

  useEffect(() => {
    if (!projectId) {
      return undefined;
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
          clamped_60m: data.clamped_60m,
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
      return undefined;
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
        setProtectHealthResolved(true);
        setLastProtectHealthSuccessAt(new Date().toISOString());
      } catch {
        if (!cancelled) {
          setProtectHealthResolved(true);
          setProtectHealthFetchFailed(lastProtectHealthSuccessAtRef.current === null);
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
      return undefined;
    }

    let cancelled = false;
    metricsRequestSeq.current += 1;
    const requestSeq = metricsRequestSeq.current;
    setLoadingMetrics(true);
    const scopeKey = `${projectId}:${selectedProvider}`;
    const scopeChanged = activeMetricsScopeRef.current !== scopeKey;
    activeMetricsScopeRef.current = scopeKey;
    const cachedSeries = seriesByScopeRef.current[scopeKey];
    setRequestsSeries(scopeChanged ? [] : (cachedSeries?.requests ?? []));
    setTokensSeries(scopeChanged ? [] : (cachedSeries?.tokens ?? []));
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
        const nextRequests = scopeChanged
          ? [data.requests_60s]
          : [...currentSeries.requests.slice(-(frontendConfig.dashboardMaxSeriesPoints - 1)), data.requests_60s];
        const nextTokens = scopeChanged
          ? [data.tokens_60s]
          : [...currentSeries.tokens.slice(-(frontendConfig.dashboardMaxSeriesPoints - 1)), data.tokens_60s];
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
      return undefined;
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
        if (selectedProvider === "all") {
          mergeProjectWarmState(projectId, {
            providers,
            incidents: data,
          });
        }
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
      return undefined;
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
    tone: ProtectStatus | "checking";
  }>(() => {
    if (!projectId) {
      return {
        label: "Awaiting traffic",
        tone: "awaiting",
      };
    }
    if (loadingProjects || !setupStatusResolved) {
      return {
        label: "Checking",
        tone: "checking",
      };
    }
    if (setupStage !== "complete") {
      return {
        label: "Awaiting traffic",
        tone: "awaiting",
      };
    }
    if (!protectHealthResolved) {
      return {
        label: "Checking",
        tone: "checking",
      };
    }
    if (protectHealthFetchFailed) {
      return {
        label: "Unavailable",
        tone: "unavailable",
      };
    }
    if (
      lastProtectHealthSuccessAt &&
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
  }, [lastProtectHealthSuccessAt, loadingProjects, projectId, protectHealth, protectHealthFetchFailed, protectHealthResolved, setupStage, setupStatusResolved]);

  return (
    <main className="dashboard">
      <div className="dashboard-content dashboard-home-content">
        <section
          className="dashboard-hero"
          aria-hidden={hideDashboardHero || undefined}
          style={hideDashboardHero ? { visibility: "hidden", pointerEvents: "none" } : undefined}
        >
          <div className="dashboard-hero-left">
            <h1 className="page-title">LLM Control Center</h1>
            <p className="page-subtitle">Real-time monitoring and protection</p>
            <div className="hero-subtitle-divider" aria-hidden="true" />
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

        <section className={`dashboard-banner-slot${!projectId || useFullWidthSetupBanner ? " dashboard-banner-slot--banner-only" : ""}`} aria-live="polite">
          {projectId && !useFullWidthSetupBanner ? <div className="dashboard-banner-slot-spacer" aria-hidden="true" /> : null}
          <div className="dashboard-banner-rail">
            {globalBanner ? <section className="banner dashboard-floating-banner">{globalBanner}</section> : null}
            {renderSetupBanner ? (
              <section className={`setup-banner dashboard-floating-banner${setupBannerClosing ? " dashboard-floating-banner--closing" : ""}`}>
                <div className="dashboard-alert-banner-layout">
                  <div className="setup-banner-title dashboard-alert-banner-title">{setupBannerContent.title}</div>
                  <div className="setup-banner-text dashboard-alert-banner-summary">{setupBannerContent.text}</div>
                  <div className="setup-banner-actions dashboard-alert-banner-actions">
                    {setupPrimaryTarget ? (
                      <button type="button" className="modal-button modal-primary" onClick={() => navigate(setupPrimaryTarget.to)}>
                        {setupPrimaryTarget.label}
                      </button>
                    ) : null}
                    {setupSecondaryTarget ? (
                      <button type="button" className="modal-button" onClick={() => navigate(setupSecondaryTarget.to)}>
                        {setupSecondaryTarget.label}
                      </button>
                    ) : null}
                    <button type="button" className="modal-button" onClick={dismissSetupBanner}>
                      Dismiss
                    </button>
                  </div>
                </div>
              </section>
            ) : null}
            {visibleWebhookIssue ? (
              <section className={`dashboard-alert-card dashboard-floating-banner${webhookIssueBannerClosing ? " dashboard-floating-banner--closing" : ""}`}>
                <div className="dashboard-alert-banner-layout">
                  <h2 className="card-title dashboard-alert-banner-title">Webhook delivery issues in the last 24 hours</h2>
                  <p className="subtle dashboard-alert-banner-summary">
                    {visibleWebhookIssue.count} {visibleWebhookIssue.count === 1 ? "delivery failed" : "deliveries failed"}
                    {visibleWebhookIssue.lastAt ? ` • Last attempt ${formatAlertAttemptTime(visibleWebhookIssue.lastAt)}` : ""}
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

        {!projectId ? null : (
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
                  key={`${projectId ?? "none"}:${selectedProvider}:requests`}
                  values={requestsSeries}
                  color="var(--req)"
                  mode="requests"
                />
                <div className="metric-card-bottom-spacer" aria-hidden="true" />
              </Card>

              <Card>
                <h2 className="card-title">Tokens (60s)</h2>
                <p className="metric-value">{loadingMetrics && !metrics ? "..." : formatNumber(metrics?.tokens_60s ?? 0)}</p>
                <PulseMeter
                  key={`${projectId ?? "none"}:${selectedProvider}:tokens`}
                  values={tokensSeries}
                  color="var(--accent)"
                  mode="tokens"
                />
                <div className="metric-card-bottom-spacer" aria-hidden="true" />
              </Card>

              <Card>
                <h2 className="card-title">
                  <span className="label-with-tooltip tooltip-label-inline">
                    <span>Incident episodes</span>
                    <InfoTooltip
                      text={
                        <>
                          Open incidents grouped by
                          <br />
                          pattern detection window
                        </>
                      }
                    />
                  </span>
                </h2>
                <div className="protect-decisions-list">
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
                    <span className="protect-decisions-label">Block reasons</span>
                    <span className="protect-decisions-value blocked">{incidentSummary.block ?? 0}</span>
                  </div>
                </div>
              </Card>

              <Card>
                <h2 className="card-title">
                  <span className="label-with-tooltip tooltip-label-inline">
                    <span>Protect decisions (60m)</span>
                    <InfoTooltip
                      text={
                        <>
                          Raw request-level decisions
                          <br />
                          in the last 60 minutes
                        </>
                      }
                    />
                  </span>
                </h2>
                <div className="protect-decisions-list">
                  <div className="protect-decisions-row">
                    <span className="protect-decisions-label">Allowed</span>
                    <span className="protect-decisions-value">{renderMetric(protectDecisionStats?.allowed_60m)}</span>
                  </div>
                  <div className="protect-decisions-row">
                    <span className="protect-decisions-label">Clamped</span>
                    <span className="protect-decisions-value warned">{renderMetric(protectDecisionStats?.clamped_60m)}</span>
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
      </div>
    </main>
  );
}
