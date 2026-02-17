import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
  createKey,
  createProject,
  fetchIncidents,
  fetchMetrics,
  fetchProjects,
  listKeys,
  resolveIncident,
  revokeKey,
  rotateKey,
  type CreateKeyResponse,
  type IncidentItem,
  type IngestKeyItem,
  type ProjectItem,
  type RealtimeMetrics,
} from "../api/client";
import { Card } from "../components/Card";
import { IncidentItem as IncidentRow } from "../components/IncidentItem";
import { Sparkline } from "../components/Sparkline";
import { StatusPill } from "../components/StatusPill";
import { frontendConfig } from "../config";
import { formatNumber, formatRelative, formatTime } from "./dashboardUtils";

type KeysModalView = "list" | "create" | "success";
const NAME_REGEX = /^[A-Za-z0-9 _.-]+$/;
const NAME_MAX = 80;

interface DashboardProps {
  userEmail?: string | null;
  onSignOut?: () => void;
}

export function Dashboard({ userEmail = null, onSignOut }: DashboardProps): JSX.Element {
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
  const [globalBanner, setGlobalBanner] = useState<string | null>(null);

  const [showCreateProjectModal, setShowCreateProjectModal] = useState<boolean>(false);
  const [newProjectName, setNewProjectName] = useState<string>("");
  const [creatingProject, setCreatingProject] = useState<boolean>(false);
  const [createProjectError, setCreateProjectError] = useState<string | null>(null);

  const [showKeysModal, setShowKeysModal] = useState<boolean>(false);
  const [keys, setKeys] = useState<IngestKeyItem[]>([]);
  const [loadingKeys, setLoadingKeys] = useState<boolean>(false);
  const [keysError, setKeysError] = useState<string | null>(null);
  const [newKeyName, setNewKeyName] = useState<string>("");
  const [creatingKey, setCreatingKey] = useState<boolean>(false);
  const [processingKeyId, setProcessingKeyId] = useState<string | null>(null);
  const [latestPlaintextKey, setLatestPlaintextKey] = useState<CreateKeyResponse | null>(null);
  const [keysModalView, setKeysModalView] = useState<KeysModalView>("list");
  const [hasLocalDemoKey, setHasLocalDemoKey] = useState<boolean>(false);
  const [copiedAction, setCopiedAction] = useState<string | null>(null);

  const sortedIncidents = useMemo(
    () => [...incidents].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
    [incidents],
  );

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === projectId) ?? null,
    [projects, projectId],
  );

  useEffect(() => {
    const interval = window.setInterval(() => {
      setClockTick((value) => value + 1);
    }, 1000);

    return () => {
      window.clearInterval(interval);
    };
  }, []);

  const reloadProjects = async (): Promise<ProjectItem[]> => {
    const items = await fetchProjects();
    setProjects(items);
    return items;
  };

  const validateProjectName = (value: string): string | null => {
    if (!value) {
      return "Project name is required.";
    }
    if (value.length > NAME_MAX) {
      return `Project name must be ${NAME_MAX} characters or less.`;
    }
    if (/[\r\n\t]/.test(value)) {
      return "Project name contains invalid characters.";
    }
    if (!NAME_REGEX.test(value)) {
      return "Project name may include letters, numbers, spaces, underscore, dash, and dot.";
    }
    return null;
  };

  const validateKeyLabel = (value: string): string | null => {
    if (!value) {
      return "Key label is required.";
    }
    if (value.length > NAME_MAX) {
      return `Key label must be ${NAME_MAX} characters or less.`;
    }
    if (/[\r\n\t]/.test(value)) {
      return "Key label contains invalid characters.";
    }
    if (!NAME_REGEX.test(value)) {
      return "Key label may include letters, numbers, spaces, underscore, dash, and dot.";
    }
    return null;
  };

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

        if (items.length === 1) {
          setProjectId(items[0].id);
        } else {
          setProjectId(null);
          window.localStorage.removeItem(frontendConfig.dashboardSelectedProjectStorageKey);
        }
      } catch (error) {
        if (!cancelled) {
          setProjects([]);
          setProjectId(null);
          setProjectWarning(error instanceof Error ? error.message : "Could not load projects from API.");
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
    setGlobalBanner(null);

    if (!projectId) {
      window.localStorage.removeItem(frontendConfig.dashboardSelectedProjectStorageKey);
      return;
    }

    window.localStorage.setItem(frontendConfig.dashboardSelectedProjectStorageKey, projectId);
  }, [projectId]);

  useEffect(() => {
    if (!projectId) {
      setHasLocalDemoKey(false);
      return;
    }
    setHasLocalDemoKey(Boolean(window.localStorage.getItem(`llmtbg_demo_key_${projectId}`)));
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
        setGlobalBanner(null);
        setMetricsFetchFailed(false);
        const timestamp = new Date().toISOString();
        setLastMetricsSuccessAt(timestamp);
        setRequestsSeries((values) => [...values.slice(-(frontendConfig.dashboardMaxSeriesPoints - 1)), data.requests_60s]);
        setTokensSeries((values) => [...values.slice(-(frontendConfig.dashboardMaxSeriesPoints - 1)), data.tokens_60s]);
      } catch (error) {
        if (!cancelled) {
          if (error instanceof ApiError && error.status === 403) {
            setGlobalBanner("You do not have access to this project's metrics.");
            setMetricsWarning("Metrics request was forbidden.");
          } else {
            setMetricsWarning("Metrics polling failed. Showing last successful values.");
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
        setGlobalBanner(null);
        setLastIncidentsSuccessAt(new Date().toISOString());
      } catch (error) {
        if (!cancelled) {
          if (error instanceof ApiError && error.status === 403) {
            setGlobalBanner("You do not have access to this project's incidents.");
            setIncidentsWarning("Incidents request was forbidden.");
          } else {
            setIncidentsWarning("Incidents polling failed. Showing last successful values.");
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
    }, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [projectId]);

  useEffect(() => {
    if (!showKeysModal || !projectId) {
      return;
    }
    setKeysModalView("list");

    let cancelled = false;
    setLoadingKeys(true);
    setKeysError(null);

    const loadKeys = async (): Promise<void> => {
      try {
        const items = await listKeys(projectId);
        if (cancelled) {
          return;
        }
        setKeys(items);
      } catch (error) {
        if (!cancelled) {
          setKeysError(error instanceof Error ? error.message : "Could not load keys for this project.");
        }
      } finally {
        if (!cancelled) {
          setLoadingKeys(false);
        }
      }
    };

    void loadKeys();
    return () => {
      cancelled = true;
    };
  }, [showKeysModal, projectId]);

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

  const onCreateProject = async (): Promise<void> => {
    const normalized = newProjectName.trim();
    const validationError = validateProjectName(normalized);
    if (validationError) {
      setCreateProjectError(validationError);
      return;
    }
    setCreatingProject(true);
    setCreateProjectError(null);
    try {
      const created = await createProject(normalized);
      const items = await reloadProjects();
      const found = items.find((item) => item.id === created.id);
      setProjectId(found ? found.id : created.id);
      setShowCreateProjectModal(false);
      setNewProjectName("");
    } catch (error) {
      setCreateProjectError(error instanceof Error ? error.message : "Failed to create project");
    } finally {
      setCreatingProject(false);
    }
  };

  const closeKeysModal = (): void => {
    setShowKeysModal(false);
    setLatestPlaintextKey(null);
    setNewKeyName("");
    setKeysError(null);
    setKeysModalView("list");
    setCopiedAction(null);
  };

  const reloadKeys = async (): Promise<void> => {
    if (!projectId) {
      return;
    }
    const items = await listKeys(projectId);
    setKeys(items);
  };

  const onCreateKey = async (): Promise<void> => {
    if (!projectId) {
      return;
    }
    const normalized = newKeyName.trim();
    const validationError = validateKeyLabel(normalized);
    if (validationError) {
      setKeysError(validationError);
      return;
    }
    setCreatingKey(true);
    setKeysError(null);
    try {
      const created = await createKey(projectId, normalized);
      setLatestPlaintextKey(created);
      setNewKeyName("");
      await reloadKeys();
      setKeysModalView("success");
    } catch (error) {
      setKeysError(error instanceof Error ? error.message : "Failed to create key.");
    } finally {
      setCreatingKey(false);
    }
  };

  const onRevokeKey = async (keyId: string): Promise<void> => {
    if (!window.confirm("Revoke this key? It will stop working immediately.")) {
      return;
    }
    setProcessingKeyId(keyId);
    setKeysError(null);
    try {
      await revokeKey(keyId);
      await reloadKeys();
    } catch (error) {
      setKeysError(error instanceof Error ? error.message : "Failed to revoke key.");
    } finally {
      setProcessingKeyId(null);
    }
  };

  const onRotateKey = async (keyId: string): Promise<void> => {
    if (!window.confirm("Rotate this key? A new key will be created and shown once.")) {
      return;
    }
    setProcessingKeyId(keyId);
    setKeysError(null);
    try {
      const rotated = await rotateKey(keyId);
      setLatestPlaintextKey(rotated);
      await reloadKeys();
    } catch (error) {
      setKeysError(error instanceof Error ? error.message : "Failed to rotate key.");
    } finally {
      setProcessingKeyId(null);
    }
  };

  const onCopyPlaintext = async (): Promise<void> => {
    if (!latestPlaintextKey) {
      return;
    }
    await copyText(latestPlaintextKey.key, "key");
  };

  const copyText = async (value: string, actionId: string): Promise<void> => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedAction(actionId);
      window.setTimeout(() => {
        setCopiedAction((current) => (current === actionId ? null : current));
      }, 1200);
    } catch {
      setKeysError("Copy failed. Copy manually from the box.");
    }
  };

  const onCopyDemoEnvVar = async (): Promise<void> => {
    if (!latestPlaintextKey) {
      return;
    }
    await copyText(`LLMTBG_INGEST_KEY="${latestPlaintextKey.key}"`, "env");
  };

  const onSetLocalDemoKey = (): void => {
    if (!projectId || !latestPlaintextKey) {
      return;
    }
    window.localStorage.setItem(`llmtbg_demo_key_${projectId}`, latestPlaintextKey.key);
    setHasLocalDemoKey(true);
  };

  const isApiConnected = Boolean(
    lastMetricsSuccessAt && !metricsFetchFailed && Date.now() - new Date(lastMetricsSuccessAt).getTime() <= 10_000,
  );

  void clockTick;

  return (
    <main className="dashboard">
      <header className="top-header">
        <div className="brand-cluster">
          <p className="subtle top-brand">LLMTokenBurnGuard</p>
        </div>
        {userEmail ? (
          <div className="user-menu">
            <span className="user-chip">
              <span className="user-chip-label">Signed in as</span>{" "}
              <span className="user-chip-email">{userEmail}</span>
            </span>
            <button type="button" className="modal-button auth-signout" onClick={onSignOut}>
              Sign out
            </button>
          </div>
        ) : null}
      </header>

      <header className="header-row">
        <div>
          <h1 className="title">LLMTokenBurnGuard Dashboard</h1>
          <p className="subtle">Incident-first runtime safety overview</p>
        </div>
        <section className="status-strip">
          <StatusPill connected={isApiConnected} />
          <div className="status-row subtle">
            <span className="status-label">Metrics updated:</span>
            <span className="status-value">{formatTime(lastMetricsSuccessAt)}</span>
          </div>
          <div className="status-row subtle">
            <span className="status-label">Incidents updated:</span>
            <span className="status-value">{formatTime(lastIncidentsSuccessAt)}</span>
          </div>
        </section>
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
        <button type="button" className="toolbar-button" onClick={() => setShowCreateProjectModal(true)}>
          New Project
        </button>
        <button type="button" className="toolbar-button" onClick={() => setShowKeysModal(true)} disabled={!projectId}>
          Keys
        </button>
      </section>

      {projectWarning ? <p className="warning-text">{projectWarning}</p> : null}
      {metricsWarning ? <p className="warning-text">{metricsWarning}</p> : null}
      {incidentsWarning ? <p className="warning-text">{incidentsWarning}</p> : null}
      {globalBanner ? <section className="banner">{globalBanner}</section> : null}
      {projectId && hasLocalDemoKey ? <p className="subtle">Demo key set locally (no secret shown).</p> : null}

      {!projectId ? (
        <section className="empty">
          <p>Select a project to see realtime metrics.</p>
          {projects.length === 0 ? (
            <>
              <p>Create your first project to start collecting metrics.</p>
              <button type="button" onClick={() => setShowCreateProjectModal(true)}>
                Create your first project
              </button>
            </>
          ) : (
            <p>Select a project to view metrics.</p>
          )}
        </section>
      ) : null}

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

      {showCreateProjectModal ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal">
            <h2 className="section-title">Create Project</h2>
            <p className="subtle">Used for grouping metrics and keys.</p>
            <input
              className="text-input"
              value={newProjectName}
              onChange={(event) => setNewProjectName(event.target.value)}
              placeholder="Project name"
            />
            {createProjectError ? <p className="warning-text">{createProjectError}</p> : null}
            <div className="modal-actions">
              <button type="button" className="modal-button" onClick={() => setShowCreateProjectModal(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="modal-button modal-primary"
                onClick={() => void onCreateProject()}
                disabled={creatingProject}
              >
                {creatingProject ? "Creating..." : "Create"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {showKeysModal ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal modal-keys">
            <h2 className="section-title">Ingest Keys - {selectedProject?.name ?? "Project"}</h2>
            <p className="subtle">Use these keys in your SDK via header: X-Project-Ingest-Key</p>

            {keysModalView === "list" ? (
              <>
                <div className="modal-actions-left">
                  <button
                    type="button"
                    className="modal-button modal-primary"
                    onClick={() => {
                      setKeysError(null);
                      setNewKeyName("");
                      setKeysModalView("create");
                    }}
                  >
                    Create key
                  </button>
                </div>

                {keysError ? <p className="warning-text">{keysError}</p> : null}
                {loadingKeys ? <p className="subtle">Loading keys...</p> : null}

                {!loadingKeys ? (
                  <div className="keys-list">
                    <div className="key-row key-row-header">
                      <span className="subtle">Label (env)</span>
                      <span className="subtle">Status</span>
                      <span className="subtle">Last 4</span>
                      <span className="subtle">Created</span>
                      <span className="subtle key-actions-col">Actions</span>
                    </div>
                    {keys.length === 0 ? <p className="subtle">No keys yet.</p> : null}
                    {keys.map((key) => (
                      <div className="key-row key-row-data" key={key.id}>
                        <span className="key-name">{key.name}</span>
                        <span className={`badge ${key.status === "active" ? "low" : "high"}`}>{key.status}</span>
                        <span className="subtle mono">{key.last4 ?? "----"}</span>
                        <span className="subtle" title={key.created_at}>
                          {formatRelative(key.created_at)}
                        </span>
                        {key.status === "active" ? (
                          <div className="key-actions">
                            <button
                              type="button"
                              className="modal-button key-action-btn"
                              onClick={() => void onRotateKey(key.id)}
                              disabled={processingKeyId === key.id}
                            >
                              Rotate
                            </button>
                            <button
                              type="button"
                              className="modal-button key-action-btn"
                              onClick={() => void onRevokeKey(key.id)}
                              disabled={processingKeyId === key.id}
                            >
                              Revoke
                            </button>
                          </div>
                        ) : (
                          <span className="subtle key-actions-col">-</span>
                        )}
                      </div>
                    ))}
                  </div>
                ) : null}

                <div className="modal-actions">
                  <button type="button" className="modal-button" onClick={closeKeysModal}>
                    Close
                  </button>
                </div>
              </>
            ) : null}

            {keysModalView === "create" ? (
              <>
                <label htmlFor="new-key-name">Key label (environment)</label>
                <p className="subtle">Example: prod, staging, dev. This is just a label for you.</p>
                <input
                  id="new-key-name"
                  className="text-input key-input"
                  value={newKeyName}
                  onChange={(event) => setNewKeyName(event.target.value)}
                  placeholder="prod"
                />
                {keysError ? <p className="warning-text">{keysError}</p> : null}
                <div className="modal-actions">
                  <button type="button" className="modal-button" onClick={() => setKeysModalView("list")}>
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="modal-button modal-primary"
                    onClick={() => void onCreateKey()}
                    disabled={creatingKey || !projectId}
                  >
                    {creatingKey ? "Creating..." : "Create"}
                  </button>
                </div>
              </>
            ) : null}

            {keysModalView === "success" && latestPlaintextKey ? (
              <>
                <div className="secret-box">
                  <p className="warning-text">Copy this key now - you won't be able to see it again.</p>
                  <pre>{latestPlaintextKey.key}</pre>
                  <div className="secret-actions">
                    <button
                      type="button"
                      className={`modal-button ${copiedAction === "key" ? "copied" : ""}`}
                      onClick={() => void onCopyPlaintext()}
                    >
                      Copy
                    </button>
                    <button
                      type="button"
                      className={`modal-button ${copiedAction === "env" ? "copied" : ""}`}
                      onClick={() => void onCopyDemoEnvVar()}
                    >
                      Copy demo env var
                    </button>
                    <button type="button" className="modal-button" onClick={onSetLocalDemoKey}>
                      Set as active demo key for this project
                    </button>
                  </div>
                  <p className={`copy-feedback ${copiedAction === "key" || copiedAction === "env" ? "visible" : ""}`}>
                    Copied to clipboard.
                  </p>
                </div>
                <div className="use-it">
                  <p className="subtle">Use it</p>
                  <pre>{`export LLMTBG_INGEST_KEY="${latestPlaintextKey.key}"\ncd sdk-node && npm run build && node dist/demo.js`}</pre>
                  <button
                    type="button"
                    className={`modal-button ${copiedAction === "node" ? "copied" : ""}`}
                    onClick={async () => {
                      await copyText(
                        `export LLMTBG_INGEST_KEY=\"${latestPlaintextKey.key}\"\ncd sdk-node && npm run build && node dist/demo.js`,
                        "node",
                      );
                    }}
                  >
                    Copy Node demo snippet
                  </button>
                  <pre>{`export LLMTBG_INGEST_KEY="${latestPlaintextKey.key}"\ncd sdk-python && python3 demo.py`}</pre>
                  <button
                    type="button"
                    className={`modal-button ${copiedAction === "python" ? "copied" : ""}`}
                    onClick={async () => {
                      await copyText(
                        `export LLMTBG_INGEST_KEY=\"${latestPlaintextKey.key}\"\ncd sdk-python && python3 demo.py`,
                        "python",
                      );
                    }}
                  >
                    Copy Python demo snippet
                  </button>
                  <p className={`copy-feedback ${copiedAction === "node" || copiedAction === "python" ? "visible" : ""}`}>
                    Copied to clipboard.
                  </p>
                </div>
                <div className="modal-actions">
                  <button
                    type="button"
                    className="modal-button modal-primary"
                    onClick={() => {
                      setLatestPlaintextKey(null);
                      setKeysModalView("list");
                      void reloadKeys();
                    }}
                  >
                    Done
                  </button>
                </div>
              </>
            ) : null}
          </div>
        </div>
      ) : null}
    </main>
  );
}
