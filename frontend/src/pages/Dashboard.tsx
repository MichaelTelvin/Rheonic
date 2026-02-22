import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
  createKey,
  createProject,
  fetchIncidents,
  fetchMetrics,
  fetchProtectMetrics,
  fetchProjectProtect,
  fetchProjectWebhook,
  fetchProjects,
  listKeys,
  resolveIncident,
  revokeKey,
  rotateKey,
  testProjectWebhook,
  updateProjectProtect,
  updateProjectWebhook,
  type CreateKeyResponse,
  type IncidentItem,
  type IngestKeyItem,
  type ProjectItem,
  type ProjectProtectSettings,
  type ProjectWebhookSettings,
  type RealtimeMetrics,
} from "../api/client";
import { Card } from "../components/Card";
import { AppHeader } from "../components/AppHeader";
import { IncidentItem as IncidentRow } from "../components/IncidentItem";
import { Sparkline } from "../components/Sparkline";
import { frontendConfig } from "../config";
import { formatNumber, formatRelative, formatTime } from "./dashboardUtils";

type KeysModalView = "list" | "create" | "success";
const NAME_REGEX = new RegExp(frontendConfig.dashboardNamePattern);
const NAME_MAX = frontendConfig.dashboardNameMaxLength;

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
  const [clockTick, setClockTick] = useState<number>(0);
  const [globalBanner, setGlobalBanner] = useState<string | null>(null);
  const [protectSettings, setProtectSettings] = useState<ProjectProtectSettings | null>(null);
  const [showProtectModal, setShowProtectModal] = useState<boolean>(false);
  const [savingProtect, setSavingProtect] = useState<boolean>(false);
  const [protectError, setProtectError] = useState<string | null>(null);
  const [protectEnabledInput, setProtectEnabledInput] = useState<boolean>(false);
  const [protectMaxReqInput, setProtectMaxReqInput] = useState<string>("");
  const [protectMaxTokInput, setProtectMaxTokInput] = useState<string>("");
  const [protectFailModeInput, setProtectFailModeInput] = useState<"open" | "closed">("open");
  const [webhookSettings, setWebhookSettings] = useState<ProjectWebhookSettings | null>(null);
  const [webhookEnabledInput, setWebhookEnabledInput] = useState<boolean>(false);
  const [webhookUrlInput, setWebhookUrlInput] = useState<string>("");
  const [webhookSecretInput, setWebhookSecretInput] = useState<string>("");
  const [webhookSaving, setWebhookSaving] = useState<boolean>(false);
  const [webhookTesting, setWebhookTesting] = useState<boolean>(false);
  const [webhookError, setWebhookError] = useState<string | null>(null);
  const [showAlertsModal, setShowAlertsModal] = useState<boolean>(false);

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
    }, frontendConfig.dashboardClockTickMs);

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
    setProtectSettings(null);
    setWebhookSettings(null);
    setProtectDecisionStats(null);
    setProtectHealthStats(null);
    setWebhookError(null);

    if (!projectId) {
      window.localStorage.removeItem(frontendConfig.dashboardSelectedProjectStorageKey);
      return;
    }

    window.localStorage.setItem(frontendConfig.dashboardSelectedProjectStorageKey, projectId);
  }, [projectId]);

  useEffect(() => {
    if (!projectId) {
      return;
    }

    let cancelled = false;

    const loadProtectStats = async (): Promise<void> => {
      try {
        const data = await fetchProtectMetrics(projectId);
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
      return;
    }

    let cancelled = false;
    const loadProtectSettings = async (): Promise<void> => {
      try {
        const settings = await fetchProjectProtect(projectId);
        if (!cancelled) {
          setProtectSettings(settings);
        }
      } catch {
        if (!cancelled) {
          setProtectSettings(null);
        }
      }
    };

    void loadProtectSettings();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    if (!projectId) {
      return;
    }

    let cancelled = false;
    const loadWebhookSettings = async (): Promise<void> => {
      try {
        const settings = await fetchProjectWebhook(projectId);
        if (!cancelled) {
          setWebhookSettings(settings);
          setWebhookEnabledInput(settings.enabled);
          setWebhookUrlInput(settings.url ?? "");
          setWebhookSecretInput("");
          setWebhookError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setWebhookSettings(null);
          setWebhookError(error instanceof Error ? error.message : "Failed to load webhook settings.");
        }
      }
    };

    void loadWebhookSettings();
    return () => {
      cancelled = true;
    };
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
    }, frontendConfig.dashboardMetricsPollMs);

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
    }, frontendConfig.dashboardIncidentsPollMs);

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

  const openProtectModal = (): void => {
    setProtectError(null);
    setProtectEnabledInput(Boolean(protectSettings?.protect_enabled));
    setProtectMaxReqInput(
      protectSettings?.protect_max_req_per_min === null || protectSettings?.protect_max_req_per_min === undefined
        ? ""
        : String(protectSettings.protect_max_req_per_min),
    );
    setProtectMaxTokInput(
      protectSettings?.protect_max_tok_per_min === null || protectSettings?.protect_max_tok_per_min === undefined
        ? ""
        : String(protectSettings.protect_max_tok_per_min),
    );
    setProtectFailModeInput(protectSettings?.protect_fail_mode === "closed" ? "closed" : "open");
    setShowProtectModal(true);
  };

  const onSaveProtectSettings = async (): Promise<void> => {
    if (!projectId) {
      return;
    }
    const parseOptionalInt = (value: string): number | null => {
      const trimmed = value.trim();
      if (!trimmed) {
        return null;
      }
      const parsed = Number(trimmed);
      if (!Number.isInteger(parsed) || parsed < 1) {
        throw new Error("Values must be a positive integer or empty for unlimited.");
      }
      return parsed;
    };

    try {
      const protect_max_req_per_min = parseOptionalInt(protectMaxReqInput);
      const protect_max_tok_per_min = parseOptionalInt(protectMaxTokInput);
      setSavingProtect(true);
      setProtectError(null);
      const updated = await updateProjectProtect(projectId, {
        protect_enabled: protectEnabledInput,
        protect_fail_mode: protectFailModeInput,
        protect_max_req_per_min,
        protect_max_tok_per_min,
        protect_decision_timeout_ms:
          protectSettings?.protect_decision_timeout_ms ?? frontendConfig.protectDefaultDecisionTimeoutMs,
      });
      setProtectSettings(updated);
      setShowProtectModal(false);
    } catch (error) {
      setProtectError(error instanceof Error ? error.message : "Failed to save protect settings.");
    } finally {
      setSavingProtect(false);
    }
  };

  const onModeSelect = async (mode: "observe" | "protect"): Promise<void> => {
    if (!projectId) {
      return;
    }
    if (mode === "protect") {
      setProtectEnabledInput(true);
      setShowProtectModal(true);
      return;
    }
    if (!protectSettings?.protect_enabled) {
      return;
    }
    if (!window.confirm("Switch to Observe mode? Protect blocking will be disabled.")) {
      return;
    }
    try {
      const updated = await updateProjectProtect(projectId, {
        protect_enabled: false,
        protect_fail_mode: protectSettings.protect_fail_mode === "closed" ? "closed" : "open",
        protect_max_req_per_min: protectSettings.protect_max_req_per_min,
        protect_max_tok_per_min: protectSettings.protect_max_tok_per_min,
        protect_decision_timeout_ms:
          protectSettings.protect_decision_timeout_ms ?? frontendConfig.protectDefaultDecisionTimeoutMs,
      });
      setProtectSettings(updated);
      setProtectError(null);
    } catch (error) {
      setProtectError(error instanceof Error ? error.message : "Failed to update mode.");
    }
  };

  const reloadWebhookSettings = async (preserveInputs = false): Promise<void> => {
    if (!projectId) {
      return;
    }
    const settings = await fetchProjectWebhook(projectId);
    setWebhookSettings(settings);
    if (!preserveInputs) {
      setWebhookEnabledInput(settings.enabled);
      setWebhookUrlInput(settings.url ?? "");
      setWebhookSecretInput("");
    }
  };

  const onSaveWebhookSettings = async (): Promise<void> => {
    if (!projectId) {
      return;
    }
    setWebhookSaving(true);
    setWebhookError(null);
    try {
      await updateProjectWebhook(projectId, {
        enabled: webhookEnabledInput,
        url: webhookUrlInput.trim() || null,
        secret: webhookSecretInput.trim() || null,
      });
      await reloadWebhookSettings();
    } catch (error) {
      setWebhookError(error instanceof Error ? error.message : "Failed to save webhook settings.");
    } finally {
      setWebhookSaving(false);
    }
  };

  const onTestWebhook = async (): Promise<void> => {
    if (!projectId) {
      return;
    }
    const draftUrl = webhookUrlInput.trim();
    if (!draftUrl) {
      setWebhookError("Webhook URL is required for test.");
      return;
    }
    if (/\s/.test(draftUrl)) {
      setWebhookError("Webhook URL must not contain spaces.");
      return;
    }
    setWebhookTesting(true);
    setWebhookError(null);
    try {
      await testProjectWebhook(projectId, {
        url: draftUrl,
        secret: webhookSecretInput.trim() || undefined,
      });
      window.setTimeout(() => {
        void reloadWebhookSettings(true);
      }, 700);
    } catch (error) {
      setWebhookError(error instanceof Error ? error.message : "Failed to queue webhook test.");
    } finally {
      setWebhookTesting(false);
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
  const renderMetric = (value: number | null | undefined): string => (value === null || value === undefined ? "—" : String(value));
  const protectEnabled = Boolean(protectSettings?.protect_enabled);
  const webhookDraftUrl = webhookUrlInput.trim();
  const canTestWebhook = Boolean(projectId) && webhookDraftUrl.length > 0 && !webhookTesting;
  const allowCountLabel = renderMetric(protectDecisionStats?.allowed_60m);
  const warnCountLabel = renderMetric(protectDecisionStats?.warned_60m);
  const blockCountLabel = renderMetric(protectDecisionStats?.blocked_60m);
  const p50Label = renderMetric(protectHealthStats?.p50_ms);
  const p95Label = renderMetric(protectHealthStats?.p95_ms);
  const decisionTimeoutsLabel = renderMetric(protectHealthStats?.decision_timeouts_60m);

  void clockTick;

  return (
    <>
      <AppHeader userEmail={userEmail} onSignOut={onSignOut} />
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
                  <span className={`status-row-value ${protectSettings?.protect_enabled ? "protect-on" : "protect-off"}`}>
                    {protectSettings?.protect_enabled ? "On" : "Off"}
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

          <section className="dashboard-controls">
            <div className="controls-left">
              <div className="toolbar">
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
                <button type="button" className="toolbar-button toolbar-button-new-project" onClick={() => setShowCreateProjectModal(true)}>
                  New Project
                </button>
              </div>
            </div>
            <div className="controls-right">
              <button
                type="button"
                className="toolbar-button toolbar-button-compact"
                onClick={() => setShowKeysModal(true)}
                disabled={!projectId}
              >
                Keys
              </button>
              <button
                type="button"
                className="toolbar-button toolbar-button-compact"
                onClick={() => setShowAlertsModal(true)}
                disabled={!projectId}
              >
                Alerts
              </button>
              <button
                type="button"
                className={`protection-toggle-btn btn-protect enable-protect-btn ${protectEnabled ? "is-enabled active" : "is-off"}`}
                onClick={openProtectModal}
                disabled={!projectId}
              >
                {protectEnabled ? "Configure protection" : "Enable protection"}
              </button>
            </div>
          </section>
          <div className="architecture-links" aria-label="Architecture diagrams">
            <span className="architecture-links-label">Architecture diagrams:</span>
            <a href="/architecture/incident_flow.svg" target="_blank" rel="noreferrer">
              Incident flow
            </a>
            <span aria-hidden="true">·</span>
            <a href="/architecture/protect_decision_flow.svg" target="_blank" rel="noreferrer">
              Protect decision flow
            </a>
          </div>

          {projectWarning ? <p className="warning-text">{projectWarning}</p> : null}
          {incidentsWarning ? <p className="warning-text">{incidentsWarning}</p> : null}
          {globalBanner ? <section className="banner">{globalBanner}</section> : null}
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
                      <span className="protect-decisions-value">{allowCountLabel}</span>
                    </div>
                    <div className="protect-decisions-row">
                      <span className="protect-decisions-label">Warned</span>
                      <span className="protect-decisions-value warned">{warnCountLabel}</span>
                    </div>
                    <div className="protect-decisions-row">
                      <span className="protect-decisions-label">Blocked</span>
                      <span className="protect-decisions-value blocked">{blockCountLabel}</span>
                    </div>
                  </div>
                </Card>

                <Card>
                  <h2 className="card-title">Decisions latency (60m)</h2>
                  <div className="protect-decisions-list">
                    <div className="protect-decisions-row">
                      <span className="protect-decisions-label">P50 latency (ms)</span>
                      <span className="protect-decisions-value">{p50Label}</span>
                    </div>
                    <div className="protect-decisions-row">
                      <span className="protect-decisions-label">P95 latency (ms)</span>
                      <span className="protect-decisions-value">{p95Label}</span>
                    </div>
                    <div className="protect-decisions-row">
                      <span className="protect-decisions-label">Timeouts</span>
                      <span className="protect-decisions-value blocked">{decisionTimeoutsLabel}</span>
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
        </div>

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

      {showProtectModal ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal">
            <h2 className="section-title">Protect settings</h2>
            <label htmlFor="protect-mode-select">Mode</label>
            <select
              id="protect-mode-select"
              value={protectEnabledInput ? "protect" : "observe"}
              onChange={(event) => setProtectEnabledInput(event.target.value === "protect")}
            >
              <option value="observe">Observe</option>
              <option value="protect">Protect</option>
            </select>

            <label htmlFor="protect-max-req">Max requests per minute</label>
            <input
              id="protect-max-req"
              className="text-input"
              type="number"
              min={1}
              placeholder="Unlimited"
              value={protectMaxReqInput}
              onChange={(event) => setProtectMaxReqInput(event.target.value)}
            />

            <label htmlFor="protect-max-tok">Max tokens per minute</label>
            <input
              id="protect-max-tok"
              className="text-input"
              type="number"
              min={1}
              placeholder="Unlimited"
              value={protectMaxTokInput}
              onChange={(event) => setProtectMaxTokInput(event.target.value)}
            />

            <fieldset className="protect-fail-mode">
              <legend>Fail mode</legend>
              <label>
                <input
                  type="radio"
                  name="protect-fail-mode"
                  value="open"
                  checked={protectFailModeInput === "open"}
                  onChange={() => setProtectFailModeInput("open")}
                />
                Fail-open
              </label>
              <label>
                <input
                  type="radio"
                  name="protect-fail-mode"
                  value="closed"
                  checked={protectFailModeInput === "closed"}
                  onChange={() => setProtectFailModeInput("closed")}
                />
                Fail-closed
              </label>
            </fieldset>

            {protectError ? <p className="warning-text">{protectError}</p> : null}
            <div className="modal-actions">
              <button type="button" className="modal-button" onClick={() => setShowProtectModal(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="modal-button modal-primary"
                onClick={() => void onSaveProtectSettings()}
                disabled={savingProtect || !projectId}
              >
                {savingProtect ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {showAlertsModal ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal">
            <h2 className="section-title">Alerts</h2>
            <div className="alerts-grid">
              <label className="alerts-toggle">
                <input
                  type="checkbox"
                  checked={webhookEnabledInput}
                  disabled={!projectId || webhookSaving}
                  onChange={(event) => setWebhookEnabledInput(event.target.checked)}
                />
                Enabled
              </label>
              <div className="alerts-field">
                <label htmlFor="webhook-url">Webhook URL</label>
                <input
                  id="webhook-url"
                  className="text-input"
                  type="url"
                  placeholder="https://..."
                  value={webhookUrlInput}
                  onChange={(event) => setWebhookUrlInput(event.target.value)}
                  disabled={!projectId || webhookSaving}
                />
              </div>
              <div className="alerts-field">
                <label htmlFor="webhook-secret">Secret (optional)</label>
                <input
                  id="webhook-secret"
                  className="text-input"
                  type="password"
                  placeholder={webhookSettings?.has_secret ? "•••••••• (leave blank to keep)" : "optional"}
                  value={webhookSecretInput}
                  onChange={(event) => setWebhookSecretInput(event.target.value)}
                  disabled={!projectId || webhookSaving}
                />
              </div>
              <p className="alerts-status">
                Last delivery:
                {" "}
                <span className={webhookSettings?.last_status === "failed" ? "alerts-failed" : "alerts-success"}>
                  {webhookSettings?.last_status ? webhookSettings.last_status : "—"}
                </span>
                {" "}
                <span>{webhookSettings?.last_at ? formatTime(webhookSettings.last_at) : "—"}</span>
              </p>
              {webhookError ? <p className="warning-text">{webhookError}</p> : null}
              <div className="modal-actions">
                <button type="button" className="modal-button" onClick={() => setShowAlertsModal(false)}>
                  Close
                </button>
                <button
                  type="button"
                  className="modal-button"
                  onClick={() => void onTestWebhook()}
                  disabled={!canTestWebhook}
                >
                  {webhookTesting ? "Testing..." : "Test webhook"}
                </button>
                <button
                  type="button"
                  className="modal-button modal-primary"
                  onClick={() => void onSaveWebhookSettings()}
                  disabled={!projectId || webhookSaving}
                >
                  {webhookSaving ? "Saving..." : "Save"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
      </main>
    </>
  );
}
