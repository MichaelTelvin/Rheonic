import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
  fetchProjectProtect,
  fetchProjectWebhook,
  testProjectWebhook,
  updateProjectWebhook,
  type ProjectWebhookSettings,
} from "../api/client";
import { Card } from "../components/Card";
import { FormColumn } from "../components/FormColumn";
import { UnsavedChangesToast } from "../components/UnsavedChangesToast";
import { showAppToast } from "../components/AppToastHost";
import { useAuthContext } from "../context/AuthContext";
import { useProjectContext } from "../context/ProjectContext";
import { useUnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";

function formatDateTime(iso: string | null): string {
  if (!iso) {
    return "—";
  }
  const value = new Date(iso);
  if (Number.isNaN(value.getTime())) {
    return "—";
  }
  return value.toLocaleString();
}

function statusUpdated(previous: ProjectWebhookSettings | null, next: ProjectWebhookSettings): boolean {
  if (!previous) {
    return Boolean(next.last_status || next.last_at);
  }
  return next.last_status !== previous.last_status || next.last_at !== previous.last_at;
}

const SAMPLE_WARN_PAYLOAD = JSON.stringify(
  {
    event: "protection.warn",
    project_id: "proj_123",
    reason: "retry_storm",
    provider: "openai",
    model: "gpt-4o-mini",
    environment: "staging",
    sent_at: "2026-03-17T06:23:20Z",
    requests_60s: 12,
    tokens_60s: 640,
    req_cap: 400,
    tok_cap: 1700,
    estimated_next_tokens: 120,
    apply_clamp_enabled: false,
    clamp: {
      recommended_max_output_tokens: 64,
      applied: false,
    },
  },
  null,
  2,
);

export function Alerts(): JSX.Element {
  const { projectId } = useProjectContext();
  const { user } = useAuthContext();
  const webhookTestMarkerKey = projectId ? `rheonic:webhookTestAt:${projectId}` : null;

  const [webhookSettings, setWebhookSettings] = useState<ProjectWebhookSettings | null>(null);
  const [webhookEnabledInput, setWebhookEnabledInput] = useState<boolean>(false);
  const [emailEnabledInput, setEmailEnabledInput] = useState<boolean>(false);
  const [webhookUrlInput, setWebhookUrlInput] = useState<string>("");
  const [webhookSaving, setWebhookSaving] = useState<boolean>(false);
  const [webhookTesting, setWebhookTesting] = useState<boolean>(false);
  const [webhookError, setWebhookError] = useState<string | null>(null);
  const [protectEnabled, setProtectEnabled] = useState<boolean>(false);
  const [loadingSettings, setLoadingSettings] = useState<boolean>(true);
  const [showPayloadModal, setShowPayloadModal] = useState<boolean>(false);
  const [payloadCopied, setPayloadCopied] = useState<boolean>(false);
  const accountEmail = user?.email ?? "your account email";

  const reloadWebhookSettings = async (preserveInputs = false, showLoading = true): Promise<void> => {
    if (!projectId) {
      return;
    }
    if (showLoading) {
      setLoadingSettings(true);
    }
    try {
      const [settings, protectSettings] = await Promise.all([fetchProjectWebhook(projectId), fetchProjectProtect(projectId)]);
      setWebhookSettings(settings);
      setProtectEnabled(Boolean(protectSettings.protect_enabled));
      if (!preserveInputs) {
        setWebhookEnabledInput(settings.enabled);
        setEmailEnabledInput(Boolean(settings.email_enabled));
        setWebhookUrlInput(settings.url ?? "");
      }
    } finally {
      if (showLoading) {
        setLoadingSettings(false);
      }
    }
  };

  useEffect(() => {
    if (!projectId) {
      setWebhookSettings(null);
      setWebhookError(null);
      setProtectEnabled(false);
      setLoadingSettings(false);
      return;
    }

    let cancelled = false;
    const loadSettings = async (): Promise<void> => {
      setLoadingSettings(true);
      try {
        const [settings, protectSettings] = await Promise.all([
          fetchProjectWebhook(projectId),
          fetchProjectProtect(projectId),
        ]);
        if (cancelled) {
          return;
        }
        setWebhookSettings(settings);
        setProtectEnabled(Boolean(protectSettings.protect_enabled));
        setWebhookEnabledInput(settings.enabled);
        setEmailEnabledInput(Boolean(settings.email_enabled));
        setWebhookUrlInput(settings.url ?? "");
        setWebhookError(null);
      } catch (error) {
        if (!cancelled) {
          setWebhookSettings(null);
          setWebhookError(error instanceof Error ? error.message : "Failed to load webhook settings.");
        }
      } finally {
        if (!cancelled) {
          setLoadingSettings(false);
        }
      }
    };

    void loadSettings();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const canTestWebhook = useMemo(
    () =>
      Boolean(projectId)
      && webhookUrlInput.trim().length > 0
      && !webhookTesting
      && !webhookSaving,
    [projectId, webhookUrlInput, webhookTesting, webhookSaving],
  );
  const controlsDisabled = !projectId;
  const saveControlsDisabled = !projectId || webhookSaving;
  const hasUnsavedChanges = useMemo(() => {
    if (!webhookSettings) {
      return false;
    }
    const savedUrl = (webhookSettings.url ?? "").trim();
    const currentUrl = webhookUrlInput.trim();
    return (
      webhookEnabledInput !== webhookSettings.enabled
      || emailEnabledInput !== Boolean(webhookSettings.email_enabled)
      || currentUrl !== savedUrl
    );
  }, [
    webhookSettings,
    webhookEnabledInput,
    emailEnabledInput,
    webhookUrlInput,
  ]);

  const discardUnsavedChanges = (): void => {
    if (!webhookSettings) {
      return;
    }
    setWebhookEnabledInput(Boolean(webhookSettings.enabled));
    setEmailEnabledInput(Boolean(webhookSettings.email_enabled));
    setWebhookUrlInput(webhookSettings.url ?? "");
    setWebhookError(null);
  };

  const saveWebhookSettings = async (emitToast = true): Promise<void> => {
    if (!projectId) {
      return;
    }
    setWebhookSaving(true);
    setWebhookError(null);
    try {
      await updateProjectWebhook(projectId, {
        enabled: webhookEnabledInput,
        email_enabled: emailEnabledInput,
        url: webhookUrlInput.trim() || null,
      });
      await reloadWebhookSettings(false, false);
      if (emitToast) {
        showAppToast("Saved");
      }
    } catch (error) {
      setWebhookError(error instanceof Error ? error.message : "Failed to save webhook settings.");
      if (emitToast) {
        showAppToast("Action failed. Try again");
      }
      throw error;
    } finally {
      setWebhookSaving(false);
    }
  };

  const onSaveWebhookSettings = async (): Promise<void> => {
    await saveWebhookSettings(true);
  };

  const {
    showPrompt: showUnsavedPrompt,
    onSaveAndContinue,
    onDiscardAndContinue,
  } = useUnsavedChangesGuard({
    isDirty: hasUnsavedChanges,
    onSave: onSaveWebhookSettings,
    onDiscard: discardUnsavedChanges,
  });

  const onTestWebhook = async (): Promise<void> => {
    if (!projectId) {
      return;
    }
    setWebhookTesting(true);
    setWebhookError(null);
    try {
      if (webhookTestMarkerKey) {
        window.localStorage.setItem(webhookTestMarkerKey, String(Date.now()));
      }
      const baseline = webhookSettings;
      await testProjectWebhook(projectId, {
        url: webhookUrlInput.trim() || undefined,
      });
      let latest: ProjectWebhookSettings | null = null;
      for (let attempt = 0; attempt < 10; attempt += 1) {
        await new Promise((resolve) => {
          window.setTimeout(resolve, 700);
        });
        latest = await fetchProjectWebhook(projectId);
        if (statusUpdated(baseline, latest)) {
          break;
        }
      }
      if (latest) {
        setWebhookSettings(latest);
      }
      if (latest?.last_status === "success") {
        showAppToast("Webhook test succeeded");
      } else {
        showAppToast("Webhook test failed");
      }
    } catch (error) {
      if (error instanceof ApiError && error.status) {
        showAppToast(`Webhook test failed (HTTP ${error.status})`);
      } else {
        showAppToast("Webhook test failed");
      }
      setWebhookError(error instanceof Error ? error.message : "Failed to queue webhook test.");
    } finally {
      setWebhookTesting(false);
    }
  };

  const onCopyPayload = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(SAMPLE_WARN_PAYLOAD);
      setPayloadCopied(true);
      window.setTimeout(() => setPayloadCopied(false), 1200);
    } catch {
      setPayloadCopied(false);
      showAppToast("Copy failed");
    }
  };

  if (!projectId) {
    return (
      <main className="dashboard alerts-dashboard">
        <div className="dashboard-content page-stack">
          <h1 className="page-title">Alerts</h1>
          <section className="empty">Select a project to configure webhook alerts.</section>
        </div>
      </main>
    );
  }
  const initialLoading = loadingSettings && webhookSettings === null;

  return (
    <main className="dashboard alerts-dashboard">
      <div className="dashboard-content page-stack alerts-page-stack">
        <section>
          <h1 className="page-title">Alerts</h1>
          <p className="page-subtitle">Configure lifecycle alert routes for email and webhook delivery</p>
        </section>

        <div className="alerts-cards-grid">
          <Card className={`form-card card--form alerts-webhook-card${initialLoading ? " card-loading-shell" : ""}`}>
            {initialLoading ? (
              <>
                <h2 className="section-title">Alert routes</h2>
                <p className="subtle card-loading-copy">Loading alert settings...</p>
              </>
            ) : (
              <FormColumn testId="alerts-form-column">
                <div className={`alerts-routes-form ${controlsDisabled ? "is-disabled" : ""}`}>
                <fieldset className={`protect-fail-mode alerts-route-section alerts-route-section--plain ${!protectEnabled ? "is-disabled" : ""}`}>
                  <legend>Email</legend>
                  <p className="alerts-intro">Protect mode only. Sends lifecycle alerts to your account email.</p>
                  <label htmlFor="alerts-email-enabled-toggle" className="alerts-toggle-row">
                    <span className="toggle-switch">
                      <input
                        id="alerts-email-enabled-toggle"
                        type="checkbox"
                        checked={emailEnabledInput}
                        disabled={saveControlsDisabled || !protectEnabled}
                        onChange={(event) => setEmailEnabledInput(event.target.checked)}
                        role="switch"
                      />
                      <span className="toggle-switch-track" aria-hidden="true" />
                    </span>
                    <span className="alerts-toggle-state">{emailEnabledInput ? "On" : "Off"}</span>
                  </label>
                  <div className="alerts-recipient-block">
                    <span className="alerts-recipient-label">Recipient:</span>
                    <span className="alerts-recipient-value">{accountEmail}</span>
                  </div>
                </fieldset>

                <fieldset className={`protect-fail-mode alerts-route-section alerts-route-section--plain ${controlsDisabled ? "is-disabled" : ""}`}>
                  <legend>Webhook</legend>
                  <p className="alerts-intro">Observe and Protect modes. Delivers lifecycle alerts to your endpoint.</p>
                  <label htmlFor="alerts-enabled-toggle" className="alerts-toggle-row">
                    <span className="toggle-switch">
                      <input
                        id="alerts-enabled-toggle"
                        type="checkbox"
                        checked={webhookEnabledInput}
                        disabled={saveControlsDisabled}
                        onChange={(event) => setWebhookEnabledInput(event.target.checked)}
                        role="switch"
                      />
                      <span className="toggle-switch-track" aria-hidden="true" />
                    </span>
                    <span className="alerts-toggle-state">{webhookEnabledInput ? "On" : "Off"}</span>
                  </label>
                  <div className="alerts-webhook-body">
                    <div className="alerts-webhook-main">
                      <div className="form-field">
                        <label htmlFor="webhook-url" title="HTTPS endpoint that receives RHEONIC webhook events.">
                          <span className="alerts-label-inline">
                            <span>Webhook URL</span>
                            {webhookTesting ? <span className="alerts-inline-spinner" aria-label="Testing webhook" /> : null}
                          </span>
                        </label>
                        <input
                          id="webhook-url"
                          className={`text-input alerts-webhook-input ${webhookError ? "input-error" : ""}`}
                          type="url"
                          placeholder="https://..."
                          value={webhookUrlInput}
                          onChange={(event) => setWebhookUrlInput(event.target.value)}
                          disabled={saveControlsDisabled || webhookTesting}
                          title={webhookUrlInput || undefined}
                        />
                      </div>

                      <div className="alerts-actions-row alerts-actions-row--inline alerts-actions-row--webhook-controls">
                        <div className="modal-actions form-actions alerts-route-buttons alerts-route-buttons--left">
                          <button
                            type="button"
                            className="modal-button action-btn"
                            onClick={() => setShowPayloadModal(true)}
                            disabled={controlsDisabled}
                          >
                            View payload
                          </button>
                          <button
                            type="button"
                            className="modal-button action-btn"
                            onClick={() => void onTestWebhook()}
                            disabled={!canTestWebhook}
                          >
                            {webhookTesting ? "Testing..." : "Test webhook"}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="alerts-actions-row alerts-actions-row--status-only">
                    <div className="alerts-status">
                      <div className="alerts-status-row">
                        <span className="alerts-status-label">Last live webhook delivery:</span>
                        <span className={webhookSettings?.last_status === "failed" ? "alerts-failed" : "alerts-success"}>
                          {webhookSettings?.last_status ? webhookSettings.last_status : "—"}
                        </span>
                      </div>
                      <div className="alerts-status-row">
                        <span className="alerts-status-label">Dispatch time:</span>
                        <span>{formatDateTime(webhookSettings?.last_at ?? null)}</span>
                      </div>
                    </div>
                  </div>
                </fieldset>

                <div className="modal-actions form-actions alerts-route-buttons alerts-route-buttons--left alerts-save-row">
                  <button
                    type="button"
                    className="modal-button modal-primary action-btn"
                    onClick={() => void onSaveWebhookSettings()}
                    disabled={saveControlsDisabled}
                  >
                    {webhookSaving ? "Saving..." : "Save alerts"}
                  </button>
                </div>
                </div>
                <p className="form-error-slot alerts-error-slot">{webhookError ?? "\u00A0"}</p>
              </FormColumn>
            )}
          </Card>
        </div>
        {showPayloadModal ? (
          <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="alerts-payload-title">
            <div className="modal alerts-payload-modal">
              <div className="alerts-payload-modal-header">
                <h2 id="alerts-payload-title" className="section-title">
                  Sample payload for protection warn event
                </h2>
                <button
                  type="button"
                  className="modal-button"
                  onClick={() => setShowPayloadModal(false)}
                >
                  Close
                </button>
              </div>
              <pre className="alerts-payload-code">
                <code>{SAMPLE_WARN_PAYLOAD}</code>
              </pre>
              <div className="modal-actions alerts-payload-modal-actions">
                <button type="button" className="modal-button action-btn" onClick={() => void onCopyPayload()}>
                  {payloadCopied ? "Copied" : "Copy JSON"}
                </button>
              </div>
            </div>
          </div>
        ) : null}
        <UnsavedChangesToast
          open={showUnsavedPrompt}
          busy={webhookSaving}
          onSave={() => void onSaveAndContinue()}
          onDiscard={onDiscardAndContinue}
        />
      </div>
    </main>
  );
}
