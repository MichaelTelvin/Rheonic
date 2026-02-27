import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  fetchIncidents,
  fetchMetrics,
  fetchProjectProviders,
  fetchProtectMetrics,
  type IncidentItem,
  type RealtimeMetrics,
} from "../api/client";
import { Card } from "../components/Card";
import { Sparkline } from "../components/Sparkline";
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

export function Dashboard(): JSX.Element {
  const { projectId } = useProjectContext();

  const [metrics, setMetrics] = useState<RealtimeMetrics | null>(null);
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [requestsSeries, setRequestsSeries] = useState<number[]>([]);
  const [tokensSeries, setTokensSeries] = useState<number[]>([]);
  const [loadingMetrics, setLoadingMetrics] = useState<boolean>(false);
  const [metricsWarning, setMetricsWarning] = useState<string | null>(null);
  const [lastMetricsSuccessAt, setLastMetricsSuccessAt] = useState<string | null>(null);
  const [lastIncidentsSuccessAt, setLastIncidentsSuccessAt] = useState<string | null>(null);
  const [metricsFetchFailed, setMetricsFetchFailed] = useState<boolean>(false);
  const [protectDecisionStats, setProtectDecisionStats] = useState<{
    allowed_60m: number | null;
    warned_60m: number | null;
    blocked_60m: number | null;
  } | null>(null);
  const [globalBanner, setGlobalBanner] = useState<string | null>(null);
  const [providers, setProviders] = useState<string[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>("all");
  const providerRequestSeq = useRef<number>(0);
  const metricsRequestSeq = useRef<number>(0);
  const seriesByScopeRef = useRef<Record<string, { requests: number[]; tokens: number[] }>>({});

  const incidentSummary = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const incident of incidents) {
      counts[incident.type] = (counts[incident.type] ?? 0) + 1;
    }
    return counts;
  }, [incidents]);

  useEffect(() => {
    setMetrics(null);
    setIncidents([]);
    setRequestsSeries([]);
    setTokensSeries([]);
    seriesByScopeRef.current = {};
    setMetricsWarning(null);
    setGlobalBanner(null);
    setProtectDecisionStats(null);
    setProviders([]);
    setSelectedProvider("all");
  }, [projectId]);

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

  const renderMetric = (value: number | null | undefined): string => (value === null || value === undefined ? "—" : String(value));
  const isApiConnected = Boolean(
    lastMetricsSuccessAt && !metricsFetchFailed && Date.now() - new Date(lastMetricsSuccessAt).getTime() <= 10_000,
  );

  return (
    <main className="dashboard">
      <div className="dashboard-content">
        <section className="dashboard-hero">
          <div className="dashboard-hero-left">
            <h1 className="page-title">LLM Control Center</h1>
            <p className="page-subtitle">Real-time monitoring and protection</p>
            <div className="hero-subtitle-divider" aria-hidden="true" />
          </div>
          <div className="dashboard-hero-right">
            <div className="status-panel status-panel--accent" aria-live="polite">
              <div className="status-row">
                <span className="status-row-label">API</span>
                <span className={`status-row-value ${isApiConnected ? "connected" : "disconnected"}`}>
                  {isApiConnected ? "Connected" : "Disconnected"}
                </span>
              </div>
              <div className="status-row">
                <span className="status-row-label">Metrics updated</span>
                <span className="status-row-value time-value">{formatTime(lastMetricsSuccessAt)}</span>
              </div>
              <div className="status-row">
                <span className="status-row-label">Incidents updated</span>
                <span className="status-row-value time-value">{formatTime(lastIncidentsSuccessAt)}</span>
              </div>
            </div>
          </div>
        </section>

        {globalBanner ? <section className="banner">{globalBanner}</section> : null}

        {!projectId ? (
          <section className="empty">
            <p>Select a project to see realtime metrics.</p>
          </section>
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
                <div className="meta-row">
                  <span className="metric-subtitle">Last 60 seconds</span>
                </div>
                <Sparkline values={requestsSeries} stroke="var(--req)" />
                <p className={`metric-card-warning ${metricsWarning ? "visible" : ""}`}>{metricsWarning ?? ""}</p>
              </Card>

              <Card>
                <h2 className="card-title">Tokens (60s)</h2>
                <p className="metric-value">{loadingMetrics && !metrics ? "..." : formatNumber(metrics?.tokens_60s ?? 0)}</p>
                <div className="meta-row">
                  <span className="metric-subtitle">Last 60 seconds</span>
                </div>
                <Sparkline values={tokensSeries} stroke="var(--accent)" />
                <p className={`metric-card-warning ${metricsWarning ? "visible" : ""}`}>{metricsWarning ?? ""}</p>
              </Card>

              <Card>
                <h2 className="card-title">Incidents</h2>
                <div className="protect-decisions-list">
                  <div className="protect-decisions-row">
                    <span className="protect-decisions-label">Near cap</span>
                    <span className="protect-decisions-value">{incidentSummary.near_cap ?? 0}</span>
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
      </div>
    </main>
  );
}
