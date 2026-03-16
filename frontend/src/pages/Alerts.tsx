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
import { InfoTooltip } from "../components/InfoTooltip";
import { UnsavedChangesToast } from "../components/UnsavedChangesToast";
import { showAppToast } from "../components/AppToastHost";
import { useAuthContext } from "../context/AuthContext";
import { useProjectContext } from "../context/ProjectContext";
import { useUnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";

const CUSTOM_PAYLOAD_PLACEHOLDER = '{\n  "channel_id": 653661315,\n  "text": "agent anomaly detected",\n  "parse_mode": "HTML"\n}';

function parsePayloadTemplateForEditor(value: string | null): string {
  if (!value) {
    return "";
  }
  try {
    const parsed = JSON.parse(value) as Record<string, unknown>;
    return Object.keys(parsed).length > 0 ? JSON.stringify(parsed, null, 2) : "";
  } catch {
    return "";
  }
}

function parseCustomPayload(source: string): Record<string, unknown> {
  const trimmed = source.trim();
  if (!trimmed) {
    return {};
  }
  const parsed = JSON.parse(trimmed) as unknown;
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("Custom payload must be a JSON object.");
  }
  return { ...(parsed as Record<string, unknown>) };
}

function buildPayloadTemplateJson(customPayloadText: string): string | null {
  const payload = parseCustomPayload(customPayloadText);
  return Object.keys(payload).length > 0 ? JSON.stringify(payload) : null;
}

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

export function Alerts(): JSX.Element {
  const { projectId } = useProjectContext();
  const { user } = useAuthContext();
  const webhookTestMarkerKey = projectId ? `rheonic:webhookTestAt:${projectId}` : null;

  const [webhookSettings, setWebhookSettings] = useState<ProjectWebhookSettings | null>(null);
  const [webhookEnabledInput, setWebhookEnabledInput] = useState<boolean>(false);
  const [emailEnabledInput, setEmailEnabledInput] = useState<boolean>(false);
  const [webhookUrlInput, setWebhookUrlInput] = useState<string>("");
  const [webhookSecretInput, setWebhookSecretInput] = useState<string>("");
  const [payloadEditorInput, setPayloadEditorInput] = useState<string>("");
  const [webhookSaving, setWebhookSaving] = useState<boolean>(false);
  const [webhookTesting, setWebhookTesting] = useState<boolean>(false);
  const [webhookError, setWebhookError] = useState<string | null>(null);
  const [protectEnabled, setProtectEnabled] = useState<boolean>(false);
  const [loadingSettings, setLoadingSettings] = useState<boolean>(true);
  const accountEmail = user?.email ?? "your account email";

  const reloadWebhookSettings = async (preserveInputs = false): Promise<void> => {
    if (!projectId) {
      return;
    }
    setLoadingSettings(true);
    try {
      const [settings, protectSettings] = await Promise.all([fetchProjectWebhook(projectId), fetchProjectProtect(projectId)]);
      setWebhookSettings(settings);
      setProtectEnabled(Boolean(protectSettings.protect_enabled));
      if (!preserveInputs) {
        setWebhookEnabledInput(settings.enabled);
        setEmailEnabledInput(Boolean(settings.email_enabled));
        setWebhookUrlInput(settings.url ?? "");
        setWebhookSecretInput("");
        setPayloadEditorInput(parsePayloadTemplateForEditor(settings.payload_template_json));
      }
    } finally {
      setLoadingSettings(false);
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
        setWebhookSecretInput("");
        setPayloadEditorInput(parsePayloadTemplateForEditor(settings.payload_template_json));
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
      && webhookEnabledInput
      && webhookUrlInput.trim().length > 0
      && !webhookTesting
      && !webhookSaving,
    [projectId, webhookEnabledInput, webhookUrlInput, webhookTesting, webhookSaving],
  );
  const controlsDisabled = !projectId || webhookSaving;
  const hasUnsavedChanges = useMemo(() => {
    if (!webhookSettings) {
      return false;
    }
    const savedUrl = (webhookSettings.url ?? "").trim();
    const currentUrl = webhookUrlInput.trim();
    const savedTemplate = parsePayloadTemplateForEditor(webhookSettings.payload_template_json);
    return (
      webhookEnabledInput !== webhookSettings.enabled
      || emailEnabledInput !== Boolean(webhookSettings.email_enabled)
      || currentUrl !== savedUrl
      || webhookSecretInput.trim().length > 0
      || payloadEditorInput !== savedTemplate
    );
  }, [
    webhookSettings,
    webhookEnabledInput,
    emailEnabledInput,
    webhookUrlInput,
    webhookSecretInput,
    payloadEditorInput,
  ]);

  const payloadTemplateError = useMemo(() => {
    try {
      parseCustomPayload(payloadEditorInput);
      return null;
    } catch {
      return "Custom payload must be a valid JSON object.";
    }
  }, [payloadEditorInput]);

  const discardUnsavedChanges = (): void => {
    if (!webhookSettings) {
      return;
    }
    setWebhookEnabledInput(Boolean(webhookSettings.enabled));
    setEmailEnabledInput(Boolean(webhookSettings.email_enabled));
    setWebhookUrlInput(webhookSettings.url ?? "");
    setWebhookSecretInput("");
    setPayloadEditorInput(parsePayloadTemplateForEditor(webhookSettings.payload_template_json));
    setWebhookError(null);
  };

  const saveWebhookSettings = async (emitToast = true): Promise<void> => {
    if (!projectId) {
      return;
    }
    setWebhookSaving(true);
    setWebhookError(null);
    try {
      if (payloadTemplateError) {
        setWebhookError(payloadTemplateError);
        if (emitToast) {
          showAppToast("Action failed. Try again");
        }
        return;
      }
      await updateProjectWebhook(projectId, {
        enabled: webhookEnabledInput,
        email_enabled: emailEnabledInput,
        url: webhookUrlInput.trim() || null,
        secret: webhookSecretInput.trim() || null,
        payload_template_json: buildPayloadTemplateJson(payloadEditorInput),
      });
      await reloadWebhookSettings();
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
      if (payloadTemplateError) {
        setWebhookError(payloadTemplateError);
        showAppToast("Webhook test failed");
        return;
      }
      if (webhookTestMarkerKey) {
        window.localStorage.setItem(webhookTestMarkerKey, String(Date.now()));
      }
      const baseline = webhookSettings;
      await testProjectWebhook(projectId, {
        url: webhookUrlInput.trim() || undefined,
        secret: webhookSecretInput.trim() || undefined,
        payload_template_json: buildPayloadTemplateJson(payloadEditorInput),
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

  if (loadingSettings && webhookSettings === null) {
    return (
      <main className="dashboard alerts-dashboard">
        <div className="dashboard-content page-stack alerts-page-stack">
          <section>
            <h1 className="page-title">Alerts</h1>
            <p className="page-subtitle">Configure protect lifecycle alert routes for email and webhook delivery</p>
          </section>
          <section className="empty">Loading alert settings...</section>
        </div>
      </main>
    );
  }

  return (
    <main className="dashboard alerts-dashboard">
      <div className="dashboard-content page-stack alerts-page-stack">
        <section>
          <h1 className="page-title">Alerts</h1>
          <p className="page-subtitle">Configure lifecycle alert routes for email and webhook delivery</p>
        </section>

        <div className="alerts-cards-grid">
          <Card className="form-card card--form alerts-webhook-card">
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
                        disabled={controlsDisabled || !protectEnabled}
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
                        disabled={controlsDisabled}
                        onChange={(event) => setWebhookEnabledInput(event.target.checked)}
                        role="switch"
                      />
                      <span className="toggle-switch-track" aria-hidden="true" />
                    </span>
                    <span className="alerts-toggle-state">{webhookEnabledInput ? "On" : "Off"}</span>
                  </label>
                  {!protectEnabled && webhookEnabledInput ? (
                    <p className="alerts-pending-status">Configured. Delivery starts when Protect is enabled.</p>
                  ) : null}

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
                          disabled={controlsDisabled || webhookTesting}
                          title={webhookUrlInput || undefined}
                        />
                      </div>

                      <div className="form-field">
                        <label htmlFor="webhook-secret">
                          <span className="label-with-tooltip tooltip-label-unified tooltip-label-inline">
                            <span>Secret</span>
                            <InfoTooltip text={<>Optional secret<br />for webhook verification.</>} />
                          </span>
                        </label>
                        <input
                          id="webhook-secret"
                          className="text-input alerts-webhook-input alerts-webhook-input--constrained"
                          type="password"
                          placeholder={webhookSettings?.has_secret ? "8f4a9c2e17b6d4fa (leave blank to keep)" : "8f4a9c2e17b6d4fa"}
                          value={webhookSecretInput}
                          onChange={(event) => setWebhookSecretInput(event.target.value)}
                          disabled={controlsDisabled || webhookTesting}
                        />
                      </div>

                      <div className="alerts-actions-row alerts-actions-row--inline">
                        <div className="modal-actions form-actions alerts-route-buttons alerts-route-buttons--left">
                          <button
                            type="button"
                            className="modal-button action-btn"
                            onClick={() => void onTestWebhook()}
                            disabled={!canTestWebhook}
                          >
                            {webhookTesting ? "Testing..." : "Test webhook"}
                          </button>
                        </div>
                        <p className="alerts-status">
                          <span className="alerts-status-label">Last webhook delivery</span>
                          <span className={webhookSettings?.last_status === "failed" ? "alerts-failed" : "alerts-success"}>
                            {webhookSettings?.last_status ? webhookSettings.last_status : "—"}
                          </span>
                          <span>{formatDateTime(webhookSettings?.last_at ?? null)}</span>
                        </p>
                      </div>
                    </div>

                    <div className="alerts-webhook-side">
                      <div className="form-field">
                        <label htmlFor="payload-editor">
                          <span className="label-with-tooltip tooltip-label-unified tooltip-label-inline">
                            <span>Custom payload</span>
                            <InfoTooltip text={<>Optional top-level fields<br />merged into the webhook body.</>} />
                          </span>
                        </label>
                        <textarea
                          id="payload-editor"
                          className="text-input alerts-template-textarea alerts-template-textarea--compact"
                          rows={5}
                          value={payloadEditorInput}
                          onChange={(event) => setPayloadEditorInput(event.target.value)}
                          disabled={controlsDisabled || webhookTesting}
                          placeholder={CUSTOM_PAYLOAD_PLACEHOLDER}
                        />
                      </div>
                    </div>
                  </div>
                </fieldset>

                <div className="modal-actions form-actions alerts-route-buttons alerts-route-buttons--left alerts-save-row">
                  <button
                    type="button"
                    className="modal-button modal-primary action-btn"
                    onClick={() => void onSaveWebhookSettings()}
                    disabled={controlsDisabled}
                  >
                    {webhookSaving ? "Saving..." : "Save alerts"}
                  </button>
                </div>
              </div>
              <p className="form-error-slot alerts-error-slot">{webhookError ?? payloadTemplateError ?? "\u00A0"}</p>
          </FormColumn>
        </Card>
        </div>
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
