import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  fetchIncidents,
  fetchMetrics,
  fetchProjectProviders,
  fetchProtectMetrics,
  fetchProjectProtect,
  resolveIncident,
  type IncidentItem,
  type RealtimeMetrics,
} from "../api/client";
import { Card } from "../components/Card";
import { IncidentItem as IncidentRow } from "../components/IncidentItem";
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

export function Dashboard(): JSX.Element {
  const { projectId } = useProjectContext();

  const [metrics, setMetrics] = useState<RealtimeMetrics | null>(null);
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [requestsSeries, setRequestsSeries] = useState<number[]>([]);
  const [tokensSeries, setTokensSeries] = useState<number[]>([]);
  const [resolvingIds, setResolvingIds] = useState<Set<string>>(new Set());
  const [loadingMetrics, setLoadingMetrics] = useState<boolean>(false);
  const [loadingIncidents, setLoadingIncidents] = useState<boolean>(false);
  const [metricsWarning, setMetricsWarning] = useState<string | null>(null);
  const [incidentsWarning, setIncidentsWarning] = useState<string | null>(null);
  const [lastMetricsSuccessAt, setLastMetricsSuccessAt] = useState<string | null>(null);
  const [lastIncidentsSuccessAt, setLastIncidentsSuccessAt] = useState<string | null>(null);
  const [metricsFetchFailed, setMetricsFetchFailed] = useState<boolean>(false);
  const [protectDecisionStats, setProtectDecisionStats] = useState<{
    allowed_60m: number | null;
    warned_60m: number | null;
    blocked_60m: number | null;
  } | null>(null);
  const [protectHealthStats, setProtectHealthStats] = useState<{
    p50_ms: number | null;
    p95_ms: number | null;
    decision_timeouts_60m: number | null;
  } | null>(null);
  const [globalBanner, setGlobalBanner] = useState<string | null>(null);
  const [protectEnabled, setProtectEnabled] = useState<boolean>(false);
  const [providers, setProviders] = useState<string[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>("all");
  const providerRequestSeq = useRef<number>(0);

  const sortedIncidents = useMemo(
    () => [...incidents].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
    [incidents],
  );

  useEffect(() => {
    setMetrics(null);
    setIncidents([]);
    setRequestsSeries([]);
    setTokensSeries([]);
    setMetricsWarning(null);
    setIncidentsWarning(null);
    setGlobalBanner(null);
    setProtectEnabled(false);
    setProtectDecisionStats(null);
    setProtectHealthStats(null);
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
      setProviders(items);
      setSelectedProvider((current) => (current !== "all" && !items.includes(current) ? "all" : current));
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
    const loadProtect = async (): Promise<void> => {
      try {
        const settings = await fetchProjectProtect(projectId);
        if (!cancelled) {
          setProtectEnabled(Boolean(settings.protect_enabled));
        }
      } catch {
        if (!cancelled) {
          setProtectEnabled(false);
        }
      }
    };

    void loadProtect();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

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
        setProtectHealthStats({
          p50_ms: data.decision_latency_p50_60m_ms,
          p95_ms: data.decision_latency_p95_60m_ms,
          decision_timeouts_60m: data.decision_timeouts_60m,
        });
      } catch {
        if (!cancelled) {
          setProtectDecisionStats(null);
          setProtectHealthStats(null);
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
  }, [projectId, selectedProvider]);

  useEffect(() => {
    if (!projectId) {
      setLoadingMetrics(false);
      return;
    }

    let cancelled = false;
    setLoadingMetrics(true);
    const providerQuery = selectedProvider === "all" ? undefined : selectedProvider;

    const loadMetrics = async (): Promise<void> => {
      try {
        const data = await fetchMetrics(projectId, providerQuery);
        if (cancelled) {
          return;
        }

        setMetrics(data);
        setMetricsWarning(null);
        setGlobalBanner(null);
        setMetricsFetchFailed(false);
        setLastMetricsSuccessAt(new Date().toISOString());
        setRequestsSeries((values) => [...values.slice(-(frontendConfig.dashboardMaxSeriesPoints - 1)), data.requests_60s]);
        setTokensSeries((values) => [...values.slice(-(frontendConfig.dashboardMaxSeriesPoints - 1)), data.tokens_60s]);
      } catch (error) {
        if (!cancelled) {
          if (error instanceof ApiError && error.status === 403) {
            setGlobalBanner("You do not have access to this project's metrics.");
            setMetricsWarning("Metrics request was forbidden.");
          } else {
            setMetricsWarning("Metrics polling failed.");
          }
          setMetricsFetchFailed(true);
        }
      } finally {
        if (!cancelled) {
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
  }, [projectId, selectedProvider]);

  useEffect(() => {
    if (!projectId) {
      setLoadingIncidents(false);
      return;
    }

    let cancelled = false;
    setLoadingIncidents(true);

    const loadIncidents = async (): Promise<void> => {
      try {
        const data = await fetchIncidents(projectId);
        if (cancelled) {
          return;
        }

        setIncidents(data);
        setIncidentsWarning(null);
        setGlobalBanner(null);
        setLastIncidentsSuccessAt(new Date().toISOString());
      } catch (error) {
        if (!cancelled) {
          if (error instanceof ApiError && error.status === 403) {
            setGlobalBanner("You do not have access to this project's incidents.");
            setIncidentsWarning("Incidents request was forbidden.");
          } else {
            setIncidentsWarning("Incidents polling failed.");
          }
        }
      } finally {
        if (!cancelled) {
          setLoadingIncidents(false);
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
  }, [projectId]);

  const onResolve = async (incidentId: string): Promise<void> => {
    if (!projectId) {
      return;
    }

    const previous = incidents;
    setResolvingIds((ids) => new Set(ids).add(incidentId));
    setIncidents((items) => items.filter((item) => item.id !== incidentId));

    try {
      await resolveIncident(incidentId);
      const updated = await fetchIncidents(projectId);
      setIncidents(updated);
      setIncidentsWarning(null);
      setLastIncidentsSuccessAt(new Date().toISOString());
    } catch {
      setIncidents(previous);
      setIncidentsWarning("Failed to resolve incident. Restored previous list.");
    } finally {
      setResolvingIds((ids) => {
        const next = new Set(ids);
        next.delete(incidentId);
        return next;
      });
    }
  };

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
                <span className="status-row-label">Protection</span>
                <span className={`status-row-value ${protectEnabled ? "protect-on" : "protect-off"}`}>{protectEnabled ? "On" : "Off"}</span>
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
            <section className="dashboard-controls">
              <div className="toolbar">
                <label htmlFor="dashboard-provider-select">Provider</label>
                <select
                  id="dashboard-provider-select"
                  value={selectedProvider}
                  onChange={(event) => setSelectedProvider(event.target.value)}
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

              <Card>
                <h2 className="card-title">Decisions latency (60m)</h2>
                <div className="protect-decisions-list">
                  <div className="protect-decisions-row">
                    <span className="protect-decisions-label">P50 latency (ms)</span>
                    <span className="protect-decisions-value">{renderMetric(protectHealthStats?.p50_ms)}</span>
                  </div>
                  <div className="protect-decisions-row">
                    <span className="protect-decisions-label">P95 latency (ms)</span>
                    <span className="protect-decisions-value">{renderMetric(protectHealthStats?.p95_ms)}</span>
                  </div>
                  <div className="protect-decisions-row">
                    <span className="protect-decisions-label">Timeouts</span>
                    <span className="protect-decisions-value blocked">{renderMetric(protectHealthStats?.decision_timeouts_60m)}</span>
                  </div>
                </div>
              </Card>
            </section>

            <section className="incidents-section">
              <h2 className="section-title">Open Incidents</h2>
              {loadingIncidents && sortedIncidents.length === 0 ? <p className="subtle">Loading incidents...</p> : null}
              {!loadingIncidents && sortedIncidents.length === 0 ? (
                <section className="empty">No open incidents right now. This project looks stable.</section>
              ) : null}

              <div className="list">
                {sortedIncidents.map((incident) => (
                  <IncidentRow key={incident.id} incident={incident} resolving={resolvingIds.has(incident.id)} onResolve={onResolve} />
                ))}
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
