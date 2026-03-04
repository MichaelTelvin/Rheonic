import { useEffect, useMemo, useState } from "react";

import { fetchProjectProtect, updateProjectProtect, type ProjectProtectSettings } from "../api/client";
import { Card } from "../components/Card";
import { FormColumn } from "../components/FormColumn";
import { InfoTooltip } from "../components/InfoTooltip";
import { UnsavedChangesToast } from "../components/UnsavedChangesToast";
import { showAppToast } from "../components/AppToastHost";
import { frontendConfig } from "../config";
import { useProjectContext } from "../context/ProjectContext";
import { useUnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";
import { getProtectReadiness, type ProtectReadiness } from "./protectReadiness";

export function Protect(): JSX.Element {
  const { projectId } = useProjectContext();
  const navigateTo = (path: string): void => {
    if (window.location.pathname === path) {
      return;
    }
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  const [protectSettings, setProtectSettings] = useState<ProjectProtectSettings | null>(null);
  const [savingProtect, setSavingProtect] = useState<boolean>(false);
  const [protectError, setProtectError] = useState<string | null>(null);
  const [protectEnabledInput, setProtectEnabledInput] = useState<boolean>(false);
  const [protectMaxReqInput, setProtectMaxReqInput] = useState<string>("");
  const [protectMaxTokInput, setProtectMaxTokInput] = useState<string>("");
  const [protectFailModeInput, setProtectFailModeInput] = useState<"open" | "closed">("open");
  const [applyClampInput, setApplyClampInput] = useState<boolean>(false);
  const [showEnableModal, setShowEnableModal] = useState<boolean>(false);
  const [loadingReadiness, setLoadingReadiness] = useState<boolean>(false);
  const [readinessError, setReadinessError] = useState<string | null>(null);
  const [readiness, setReadiness] = useState<ProtectReadiness | null>(null);
  const [muteFor24h, setMuteFor24h] = useState<boolean>(false);
  const [pendingWarningsCount, setPendingWarningsCount] = useState<number | null>(null);
  const [showPostEnableToast, setShowPostEnableToast] = useState<boolean>(false);
  const failModeDisabled = !protectEnabledInput;
  const sanitizeDigits = (value: string): string => value.replace(/\D+/g, "");
  const mutedStorageKey = projectId ? `rheonic:protectConfirmMuted:${projectId}` : null;
  const applyInputsFromSettings = (settings: ProjectProtectSettings): void => {
    setProtectEnabledInput(Boolean(settings.protect_enabled));
    setProtectMaxReqInput(
      settings.protect_max_req_per_min === null || settings.protect_max_req_per_min === undefined
        ? ""
        : String(settings.protect_max_req_per_min),
    );
    setProtectMaxTokInput(
      settings.protect_max_tok_per_min === null || settings.protect_max_tok_per_min === undefined
        ? ""
        : String(settings.protect_max_tok_per_min),
    );
    setProtectFailModeInput(settings.protect_fail_mode === "closed" ? "closed" : "open");
    setApplyClampInput(Boolean(settings.apply_clamp));
  };

  const readinessItems = useMemo(
    () => [
      {
        id: "limits",
        label: "Request/token limits",
        ready: Boolean(readiness?.limitsConfigured),
        readyText: "Set",
        warnText: "Not set",
        actionLabel: "Open settings",
      },
      {
        id: "notifications",
        label: "Notifications",
        ready: Boolean(readiness?.notificationsConfigured),
        readyText: "Configured",
        warnText: "Set up Email or Webhook alerts before enabling Protect.",
        actionLabel: "Open notifications",
      },
      {
        id: "traffic",
        label: "Traffic detected",
        ready: Boolean(readiness?.trafficDetected),
        readyText: "Events received",
        warnText: "No events received yet",
        actionLabel: "Open Quickstart",
      },
    ],
    [readiness],
  );

  const warningsCount = readinessItems.filter((item) => !item.ready).length;

  const refreshProtectReadiness = async (): Promise<void> => {
    if (!projectId) {
      return;
    }
    try {
      setLoadingReadiness(true);
      setReadinessError(null);
      const nextReadiness = await getProtectReadiness(projectId);
      setReadiness(nextReadiness);
    } catch (error) {
      setReadiness(null);
      setReadinessError(error instanceof Error ? error.message : "Failed to validate readiness.");
    } finally {
      setLoadingReadiness(false);
    }
  };

  const isProtectConfirmMuted = (): boolean => {
    if (!mutedStorageKey) {
      return false;
    }
    const raw = window.localStorage.getItem(mutedStorageKey);
    if (!raw) {
      return false;
    }
    const expiresAt = Number(raw);
    if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
      window.localStorage.removeItem(mutedStorageKey);
      return false;
    }
    return true;
  };

  useEffect(() => {
    if (!projectId) {
      setProtectSettings(null);
      setProtectError(null);
      return;
    }

    let cancelled = false;
    const loadSettings = async (): Promise<void> => {
      try {
        const settings = await fetchProjectProtect(projectId);
        if (cancelled) {
          return;
        }
        setProtectSettings(settings);
        applyInputsFromSettings(settings);
        setProtectError(null);
      } catch (error) {
        if (!cancelled) {
          setProtectSettings(null);
          setProtectError(error instanceof Error ? error.message : "Failed to load protect settings.");
        }
      }
    };

    void loadSettings();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    setShowEnableModal(false);
    setReadiness(null);
    setReadinessError(null);
    setMuteFor24h(false);
    setPendingWarningsCount(null);
    setShowPostEnableToast(false);
  }, [projectId]);

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
      const wasProtectEnabled = Boolean(protectSettings?.protect_enabled);
      const protect_max_req_per_min = parseOptionalInt(protectMaxReqInput);
      const protect_max_tok_per_min = parseOptionalInt(protectMaxTokInput);
      setSavingProtect(true);
      setProtectError(null);
      const updated = await updateProjectProtect(projectId, {
        protect_enabled: protectEnabledInput,
        protect_fail_mode: protectFailModeInput,
        apply_clamp: applyClampInput,
        protect_max_req_per_min,
        protect_max_tok_per_min,
        protect_decision_timeout_ms:
          protectSettings?.protect_decision_timeout_ms ?? frontendConfig.protectDefaultDecisionTimeoutMs,
      });
      setProtectSettings(updated);
      applyInputsFromSettings(updated);
      const isProtectEnabled = Boolean(updated.protect_enabled);
      if (!wasProtectEnabled && isProtectEnabled) {
        showAppToast("Protect enabled");
      } else if (wasProtectEnabled && !isProtectEnabled) {
        showAppToast("Protect disabled");
      } else {
        showAppToast("Saved");
      }
      const transitionedToProtect = !Boolean(protectSettings?.protect_enabled) && Boolean(updated.protect_enabled);
      if (transitionedToProtect) {
        let unresolvedWarnings = pendingWarningsCount;
        if (unresolvedWarnings === null) {
          try {
            const latestReadiness = await getProtectReadiness(projectId);
            unresolvedWarnings = Number(
              [latestReadiness.limitsConfigured, latestReadiness.notificationsConfigured, latestReadiness.trafficDetected].filter(
                (value) => !value,
              ).length,
            );
          } catch {
            unresolvedWarnings = 0;
          }
        }
        setShowPostEnableToast((unresolvedWarnings ?? 0) > 0);
      } else {
        setShowPostEnableToast(false);
      }
      setPendingWarningsCount(null);
      window.dispatchEvent(
        new CustomEvent("rheonic:protect-mode-updated", {
          detail: { projectId, protect_enabled: Boolean(updated.protect_enabled) },
        }),
      );
    } catch (error) {
      setProtectError(error instanceof Error ? error.message : "Failed to save protect settings.");
      showAppToast("Action failed. Try again");
    } finally {
      setSavingProtect(false);
    }
  };

  const hasUnsavedChanges = useMemo(() => {
    if (!protectSettings) {
      return false;
    }
    const savedReq = protectSettings.protect_max_req_per_min == null ? "" : String(protectSettings.protect_max_req_per_min);
    const savedTok = protectSettings.protect_max_tok_per_min == null ? "" : String(protectSettings.protect_max_tok_per_min);
    const savedFailMode = protectSettings.protect_fail_mode === "closed" ? "closed" : "open";
    return (
      protectEnabledInput !== Boolean(protectSettings.protect_enabled)
      || protectMaxReqInput.trim() !== savedReq
      || protectMaxTokInput.trim() !== savedTok
      || protectFailModeInput !== savedFailMode
      || applyClampInput !== Boolean(protectSettings.apply_clamp)
    );
  }, [
    protectSettings,
    protectEnabledInput,
    protectMaxReqInput,
    protectMaxTokInput,
    protectFailModeInput,
    applyClampInput,
  ]);

  const discardUnsavedChanges = (): void => {
    if (!protectSettings) {
      return;
    }
    applyInputsFromSettings(protectSettings);
    setProtectError(null);
    setPendingWarningsCount(null);
    setShowEnableModal(false);
  };

  const {
    showPrompt: showUnsavedPrompt,
    onSaveAndContinue,
    onDiscardAndContinue,
  } = useUnsavedChangesGuard({
    isDirty: hasUnsavedChanges,
    onSave: onSaveProtectSettings,
    onDiscard: discardUnsavedChanges,
  });

  if (!projectId) {
    return (
      <main className="dashboard">
        <div className="dashboard-content page-stack">
          <h1 className="page-title">Project settings</h1>
          <section className="empty">Select a project to configure protection rules.</section>
        </div>
      </main>
    );
  }

  const onProtectModeChange = async (nextMode: "observe" | "protect"): Promise<void> => {
    if (nextMode === "observe") {
      setProtectEnabledInput(false);
      return;
    }
    if (protectEnabledInput) {
      return;
    }
    if (isProtectConfirmMuted()) {
      setProtectEnabledInput(true);
      setPendingWarningsCount(null);
      return;
    }
    setLoadingReadiness(true);
    setReadinessError(null);
    try {
      const nextReadiness = await getProtectReadiness(projectId);
      setReadiness(nextReadiness);
      const allChecksPassed =
        Boolean(nextReadiness.limitsConfigured)
        && Boolean(nextReadiness.notificationsConfigured)
        && Boolean(nextReadiness.trafficDetected);
      if (allChecksPassed) {
        setPendingWarningsCount(0);
        setProtectEnabledInput(true);
        setShowEnableModal(false);
        return;
      }
      setShowEnableModal(true);
      setMuteFor24h(false);
    } catch (error) {
      setReadiness(null);
      setReadinessError(error instanceof Error ? error.message : "Failed to validate readiness.");
      setShowEnableModal(true);
      setMuteFor24h(false);
    } finally {
      setLoadingReadiness(false);
    }
  };

  const onEnableProtectAnyway = (): void => {
    if (muteFor24h && mutedStorageKey) {
      const expiresAt = Date.now() + 24 * 60 * 60 * 1000;
      window.localStorage.setItem(mutedStorageKey, String(expiresAt));
    }
    setPendingWarningsCount(warningsCount);
    setProtectEnabledInput(true);
    setShowEnableModal(false);
  };

  const onChecklistAction = (itemId: string): void => {
    setShowEnableModal(false);
    if (itemId === "limits") {
      const node = document.getElementById("protect-max-req");
      if (node instanceof HTMLInputElement) {
        node.focus();
      }
      return;
    }
    if (itemId === "notifications") {
      navigateTo("/app/alerts");
      return;
    }
    navigateTo("/quickstart");
  };

  return (
    <main className="dashboard">
      <div className="dashboard-content page-stack">
        <section>
          <h1 className="page-title">Project settings</h1>
          <p className="page-subtitle">Configure limits and protection behavior</p>
        </section>

        <Card className="form-card card--form">
          <h2 className="section-title">Project configuration</h2>
          <div className="protect-settings-grid" data-testid="protect-form-column">
            <FormColumn>
              <div className="form-field protect-mode">
                <label htmlFor="protect-mode-select">Project mode</label>
                <select
                  id="protect-mode-select"
                  value={protectEnabledInput ? "protect" : "observe"}
                  onChange={(event) => {
                    void onProtectModeChange(event.target.value === "protect" ? "protect" : "observe");
                    event.currentTarget.blur();
                  }}
                  title="Observe = telemetry only, Protect = preflight decisions enforced."
                >
                  <option value="observe">Observe</option>
                  <option value="protect">Protect</option>
                </select>
              </div>

              <div className="form-field protect-req">
                <label htmlFor="protect-max-req" className="label-with-tooltip tooltip-label-unified">
                  <span className="tooltip-label-inline">
                    <span>Max requests per minute</span>
                    <InfoTooltip text="Applied per provider." />
                  </span>
                </label>
                <input
                  id="protect-max-req"
                  className="text-input"
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  placeholder="Unlimited"
                  value={protectMaxReqInput}
                  onChange={(event) => setProtectMaxReqInput(sanitizeDigits(event.target.value))}
                />
              </div>

              <div className="form-field">
                <label htmlFor="protect-max-tok" className="label-with-tooltip tooltip-label-unified">
                  <span className="tooltip-label-inline">
                    <span>Max tokens per minute</span>
                    <InfoTooltip text="Applied per provider." />
                  </span>
                </label>
                <input
                  id="protect-max-tok"
                  className="text-input"
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  placeholder="Unlimited"
                  value={protectMaxTokInput}
                  onChange={(event) => setProtectMaxTokInput(sanitizeDigits(event.target.value))}
                />
              </div>
            </FormColumn>

            <FormColumn>
              <fieldset className={`protect-fail-mode ${failModeDisabled ? "is-disabled" : ""}`} disabled={failModeDisabled}>
                <legend>On guard error</legend>
                <label>
                  <input
                    type="radio"
                    name="protect-fail-mode"
                    value="open"
                    checked={protectFailModeInput === "open"}
                    onChange={() => setProtectFailModeInput("open")}
                    disabled={failModeDisabled}
                  />
                  Allow LLM request
                </label>
                <label>
                  <input
                    type="radio"
                    name="protect-fail-mode"
                    value="closed"
                    checked={protectFailModeInput === "closed"}
                    onChange={() => setProtectFailModeInput("closed")}
                    disabled={failModeDisabled}
                  />
                  Block LLM request
                </label>
              </fieldset>

              <fieldset className={`protect-fail-mode clamp-toggle-fieldset ${failModeDisabled ? "is-disabled" : ""}`} disabled={failModeDisabled}>
                <legend>
                  <span className="label-with-tooltip tooltip-label-unified tooltip-label-inline">
                    <span>Auto token clamp</span>
                    <InfoTooltip text="Apply output token clamp when near limit" />
                  </span>
                </legend>
                <label htmlFor="apply-clamp-toggle" className="clamp-toggle-row">
                  <span className="toggle-switch">
                    <input
                      id="apply-clamp-toggle"
                      type="checkbox"
                      checked={applyClampInput}
                      onChange={(event) => setApplyClampInput(event.target.checked)}
                      disabled={failModeDisabled}
                      role="switch"
                    />
                    <span className="toggle-switch-track" aria-hidden="true" />
                  </span>
                  <span>{applyClampInput ? "On" : "Off"}</span>
                </label>
              </fieldset>
            </FormColumn>
          </div>
          <p className="form-error-slot">{protectError ?? "\u00A0"}</p>
          {showPostEnableToast ? (
            <div className="protect-soft-warning-toast" role="status" aria-live="polite">
              <span>Protect enabled — some settings need attention.</span>
              <button type="button" className="modal-button" onClick={() => navigateTo("/app/settings")}>
                Open settings
              </button>
            </div>
          ) : null}
          <div className="modal-actions form-actions">
            <button
              type="button"
              className="modal-button modal-primary action-btn"
              onClick={() => void onSaveProtectSettings()}
              disabled={savingProtect || !projectId}
            >
              {savingProtect ? "Saving..." : "Save"}
            </button>
          </div>
        </Card>

        {showEnableModal ? (
          <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="protect-enable-title">
            <div className="modal protect-enable-modal">
              <h2 id="protect-enable-title" className="section-title">
                Enable Protect mode?
              </h2>
              <p className="subtle">
                We&apos;ll start making preflight decisions before provider calls. Review these items first.
              </p>
              {loadingReadiness ? <p className="subtle">Checking readiness...</p> : null}
              {readinessError ? <p className="form-error-slot">{readinessError}</p> : null}
              {!loadingReadiness && !readinessError ? (
                <div className="protect-readiness-list">
                  {readinessItems.map((item) => (
                    <div key={item.id} className={`protect-readiness-row ${item.ready ? "is-ready" : "is-warning"}`}>
                      <div className="protect-readiness-copy">
                        <p className="protect-readiness-title">
                          <span className="protect-readiness-icon" aria-hidden="true">
                            {item.ready ? "✅" : "⚠️"}
                          </span>
                          <span>{item.label}</span>
                        </p>
                        <p className="subtle">{item.ready ? item.readyText : item.warnText}</p>
                      </div>
                      {!item.ready ? (
                        <button
                          type="button"
                          className="modal-button protect-readiness-action"
                          onClick={() => onChecklistAction(item.id)}
                        >
                          {item.actionLabel}
                        </button>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}
              <label className="protect-readiness-mute">
                <input type="checkbox" checked={muteFor24h} onChange={(event) => setMuteFor24h(event.target.checked)} />
                <span>Don&apos;t show again for this project for 24h</span>
              </label>
              <div className="modal-actions">
                <button
                  type="button"
                  className="modal-button"
                  onClick={() => {
                    setProtectEnabledInput(false);
                    setShowEnableModal(false);
                  }}
                >
                  Back to Observe
                </button>
                <button type="button" className="modal-button modal-primary" onClick={onEnableProtectAnyway}>
                  Enable Protect
                </button>
                <button type="button" className="modal-button" onClick={() => void refreshProtectReadiness()}>
                  Refresh
                </button>
              </div>
            </div>
          </div>
        ) : null}
        <UnsavedChangesToast
          open={showUnsavedPrompt}
          busy={savingProtect}
          onSave={() => void onSaveAndContinue()}
          onDiscard={onDiscardAndContinue}
        />
      </div>
    </main>
  );
}
