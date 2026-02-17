import { useEffect, useMemo, useState } from "react";

import { fetchIncidents, fetchMetrics, fetchProjects, resolveIncident, type IncidentItem, type ProjectItem, type RealtimeMetrics } from "../api/client";
import { Card } from "../components/Card";
import { IncidentItem as IncidentRow } from "../components/IncidentItem";
import { Sparkline } from "../components/Sparkline";
import { StatusPill } from "../components/StatusPill";
import { frontendConfig } from "../config";
import { formatNumber, formatTime } from "./dashboardUtils";

export function Dashboard(): JSX.Element {
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<RealtimeMetrics | null>(null);
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [requestsSeries, setRequestsSeries] = useState<number[]>([]);
  const [tokensSeries, setTokensSeries] = useState<number[]>([]);
  const [resolvingIds, setResolvingIds] = useState<Set<string>>(new Set());
  const [loadingProjects, setLoadingProjects] = useState<boolean>(true);
  const [loadingMetrics, setLoadingMetrics] = useState<boolean>(false);
  const [loadingIncidents, setLoadingIncidents] = useState<boolean>(false);
  const [projectWarning, setProjectWarning] = useState<string | null>(null);
  const [metricsWarning, setMetricsWarning] = useState<string | null>(null);
  const [incidentsWarning, setIncidentsWarning] = useState<string | null>(null);
  const [lastMetricsSuccessAt, setLastMetricsSuccessAt] = useState<string | null>(null);
  const [lastIncidentsSuccessAt, setLastIncidentsSuccessAt] = useState<string | null>(null);
  const [metricsFetchFailed, setMetricsFetchFailed] = useState<boolean>(false);
  const [clockTick, setClockTick] = useState<number>(0);

  const sortedIncidents = useMemo(
    () => [...incidents].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
    [incidents],
  );

  useEffect(() => {
    const interval = window.setInterval(() => {
      setClockTick((value) => value + 1);
    }, 1000);

    return () => {
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadProjects = async (): Promise<void> => {
      try {
        const items = await fetchProjects();
        if (cancelled) {
          return;
        }

        setProjects(items);
        setProjectWarning(null);

        const storedProjectId = window.localStorage.getItem(frontendConfig.dashboardSelectedProjectStorageKey);
        if (storedProjectId && items.some((item) => item.id === storedProjectId)) {
          setProjectId(storedProjectId);
        } else {
          setProjectId(items.length > 0 ? items[0].id : null);
        }
      } catch {
        if (!cancelled) {
          setProjects([]);
          setProjectId(null);
          setProjectWarning("Could not load projects from API.");
        }
      } finally {
        if (!cancelled) {
          setLoadingProjects(false);
        }
      }
    };

    void loadProjects();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setMetrics(null);
    setIncidents([]);
    setRequestsSeries([]);
    setTokensSeries([]);
    setMetricsWarning(null);
    setIncidentsWarning(null);

    if (!projectId) {
      window.localStorage.removeItem(frontendConfig.dashboardSelectedProjectStorageKey);
      return;
    }

    window.localStorage.setItem(frontendConfig.dashboardSelectedProjectStorageKey, projectId);
  }, [projectId]);

  useEffect(() => {
    if (!projectId) {
      setLoadingMetrics(false);
      return;
    }

    let cancelled = false;
    setLoadingMetrics(true);

    const loadMetrics = async (): Promise<void> => {
      try {
        const data = await fetchMetrics(projectId);
        if (cancelled) {
          return;
        }

        setMetrics(data);
        setMetricsWarning(null);
        setMetricsFetchFailed(false);
        const timestamp = new Date().toISOString();
        setLastMetricsSuccessAt(timestamp);
        setRequestsSeries((values) => [...values.slice(-(frontendConfig.dashboardMaxSeriesPoints - 1)), data.requests_60s]);
        setTokensSeries((values) => [...values.slice(-(frontendConfig.dashboardMaxSeriesPoints - 1)), data.tokens_60s]);
      } catch {
        if (!cancelled) {
          setMetricsWarning("Metrics polling failed. Showing last successful values.");
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
    }, 2000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [projectId]);

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
        setLastIncidentsSuccessAt(new Date().toISOString());
      } catch {
        if (!cancelled) {
          setIncidentsWarning("Incidents polling failed. Showing last successful values.");
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
    }, 5000);

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

  const isApiConnected = Boolean(
    lastMetricsSuccessAt && !metricsFetchFailed && Date.now() - new Date(lastMetricsSuccessAt).getTime() <= 10_000,
  );

  void clockTick;

  return (
    <main className="dashboard">
      <header className="header-row">
        <div>
          <h1 className="title">LLMTokenBurnGuard Dashboard</h1>
          <p className="subtle">Incident-first runtime safety overview</p>
        </div>

        <div className="status-panel">
          <StatusPill connected={isApiConnected} />
          <span className="subtle">Metrics updated: {formatTime(lastMetricsSuccessAt)}</span>
          <span className="subtle">Incidents updated: {formatTime(lastIncidentsSuccessAt)}</span>
        </div>
      </header>

      <section className="toolbar">
        <label htmlFor="project-select">Project</label>
        <select
          id="project-select"
          value={projectId ?? ""}
          onChange={(event) => setProjectId(event.target.value || null)}
          disabled={loadingProjects || projects.length === 0}
        >
          {projectId ? null : <option value="">Select project</option>}
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>
      </section>

      {projectWarning ? <p className="warning-text">{projectWarning}</p> : null}
      {metricsWarning ? <p className="warning-text">{metricsWarning}</p> : null}
      {incidentsWarning ? <p className="warning-text">{incidentsWarning}</p> : null}

      {!projectId ? <section className="empty">Select a project to view metrics.</section> : null}

      {projectId ? (
        <>
          <section className="metrics-grid">
            <Card>
              <h2 className="card-title">Requests (60s)</h2>
              <p className="metric-value">{loadingMetrics && !metrics ? "..." : formatNumber(metrics?.requests_60s ?? 0)}</p>
              <div className="meta-row">
                <span className="metric-subtitle">Last 60 seconds</span>
                <span>Updated {formatTime(lastMetricsSuccessAt)}</span>
              </div>
              <Sparkline values={requestsSeries} stroke="var(--req)" />
            </Card>

            <Card>
              <h2 className="card-title">Tokens (60s)</h2>
              <p className="metric-value">{loadingMetrics && !metrics ? "..." : formatNumber(metrics?.tokens_60s ?? 0)}</p>
              <div className="meta-row">
                <span className="metric-subtitle">Last 60 seconds</span>
                <span>Updated {formatTime(lastMetricsSuccessAt)}</span>
              </div>
              <Sparkline values={tokensSeries} stroke="var(--accent)" />
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
                <IncidentRow
                  key={incident.id}
                  incident={incident}
                  resolving={resolvingIds.has(incident.id)}
                  onResolve={onResolve}
                />
              ))}
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}
