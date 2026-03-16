import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiError, fetchIncidents, fetchProjectProviders, resolveIncident, type IncidentItem } from "../api/client";
import { IncidentItem as IncidentRow } from "../components/IncidentItem";
import { frontendConfig } from "../config";
import { useProjectContext } from "../context/ProjectContext";

function formatProviderLabel(provider: string): string {
  return provider
    .split(/[_-]/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function Incidents(): JSX.Element {
  const { projectId } = useProjectContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialProvider = (searchParams.get("provider") ?? "all").toLowerCase();

  const [providers, setProviders] = useState<string[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>(initialProvider);
  const [selectedStatus, setSelectedStatus] = useState<"all" | "open" | "resolved">("open");
  const [selectedType, setSelectedType] = useState<string>("all");
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [resolvingIds, setResolvingIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<boolean>(false);
  const [warning, setWarning] = useState<string | null>(null);
  const providerRequestSeq = useRef<number>(0);

  const sortedIncidents = useMemo(
    () => [...incidents].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
    [incidents],
  );

  useEffect(() => {
    setIncidents([]);
    setWarning(null);
    setSelectedType("all");
    setSelectedStatus("open");
    setSelectedProvider((searchParams.get("provider") ?? "all").toLowerCase());
  }, [projectId, searchParams]);

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
    setLoading(true);
    const providerQuery = selectedProvider === "all" ? undefined : selectedProvider;
    const statusQuery = selectedStatus === "all" ? "all" : selectedStatus;

    const load = async (): Promise<void> => {
      try {
        const rows = await fetchIncidents(projectId, providerQuery, statusQuery);
        if (cancelled) {
          return;
        }
        setIncidents(selectedType === "all" ? rows : rows.filter((row) => row.type === selectedType));
        setWarning(null);
      } catch (error) {
        if (!cancelled) {
          if (error instanceof ApiError && error.status === 403) {
            setWarning("Incidents request was forbidden.");
          } else {
            setWarning("Incidents polling failed.");
          }
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();
    const interval = window.setInterval(() => {
      void load();
    }, frontendConfig.dashboardIncidentsPollMs);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [projectId, selectedProvider, selectedStatus, selectedType]);

  const onResolve = async (incidentId: string): Promise<void> => {
    if (!projectId) {
      return;
    }
    const previous = incidents;
    setResolvingIds((ids) => new Set(ids).add(incidentId));
    setIncidents((items) => items.filter((item) => item.id !== incidentId));
    try {
      await resolveIncident(incidentId);
      const providerQuery = selectedProvider === "all" ? undefined : selectedProvider;
      const statusQuery = selectedStatus === "all" ? "all" : selectedStatus;
      const updated = await fetchIncidents(projectId, providerQuery, statusQuery);
      setIncidents(selectedType === "all" ? updated : updated.filter((row) => row.type === selectedType));
      setWarning(null);
    } catch {
      setIncidents(previous);
      setWarning("Failed to resolve incident.");
    } finally {
      setResolvingIds((ids) => {
        const next = new Set(ids);
        next.delete(incidentId);
        return next;
      });
    }
  };

  const onProviderChange = (nextProvider: string): void => {
    setSelectedProvider(nextProvider);
    const nextParams = new URLSearchParams(searchParams);
    if (nextProvider === "all") {
      nextParams.delete("provider");
    } else {
      nextParams.set("provider", nextProvider);
    }
    setSearchParams(nextParams, { replace: true });
  };

  return (
    <main className="dashboard">
      <div className="dashboard-content page-stack">
        <section>
          <h1 className="page-title">Incidents</h1>
          <p className="page-subtitle">Review and resolve runtime incidents</p>
        </section>

        <section className="incidents-layout">
          <section className="dashboard-controls incidents-filters-row incidents-filters-shell">
            <div className="toolbar incidents-toolbar">
              <div className="incidents-filter-field">
                <label htmlFor="incidents-provider-select">Provider</label>
                <select
                  id="incidents-provider-select"
                  value={selectedProvider}
                  onChange={(event) => {
                    onProviderChange(event.target.value);
                    event.currentTarget.blur();
                  }}
                  onFocus={() => {
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

              <div className="incidents-filter-field">
                <label htmlFor="incidents-type-select">Type</label>
                <select
                  id="incidents-type-select"
                  value={selectedType}
                  onChange={(event) => {
                    setSelectedType(event.target.value);
                    event.currentTarget.blur();
                  }}
                >
                  <option value="all">All</option>
                  <option value="near_cap">Near cap</option>
                  <option value="cap_breach">Cap breach</option>
                  <option value="retry_storm">Retry storm</option>
                  <option value="loop_suspect">Loop suspect</option>
                  <option value="token_explosion">Token explosion</option>
                </select>
              </div>

              <div className="incidents-filter-field">
                <label htmlFor="incidents-status-select">Status</label>
                <select
                  id="incidents-status-select"
                  value={selectedStatus}
                  onChange={(event) => {
                    setSelectedStatus(event.target.value as "all" | "open" | "resolved");
                    event.currentTarget.blur();
                  }}
                >
                  <option value="open">Open</option>
                  <option value="resolved">Resolved</option>
                  <option value="all">All</option>
                </select>
              </div>
            </div>
          </section>

          {warning ? <p className="metric-card-warning visible">{warning}</p> : null}

          <section className="incidents-list-shell">
            <section className="incidents-scroll-panel">
              {loading && sortedIncidents.length === 0 ? <p className="subtle">Loading incidents...</p> : null}
              {sortedIncidents.length === 0 ? <section className="empty">No incidents for current filters.</section> : null}
              <div className="list">
                {sortedIncidents.map((incident) => (
                  <IncidentRow key={incident.id} incident={incident} resolving={resolvingIds.has(incident.id)} onResolve={onResolve} />
                ))}
              </div>
            </section>
          </section>
        </section>
      </div>
    </main>
  );
}
