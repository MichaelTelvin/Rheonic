import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
  fetchProjectProtect,
  fetchProjectWebhook,
  testProjectWebhook,
  updateProjectWebhook,
  type ProjectWebhookSettings,
} from "../api/client";
import { getAuthItem } from "../authStorage";
import { Card } from "../components/Card";
import { FormColumn } from "../components/FormColumn";
import { UnsavedChangesToast } from "../components/UnsavedChangesToast";
import { frontendConfig } from "../config";
import { useProjectContext } from "../context/ProjectContext";
import { useUnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";

type TestStatus = {
  kind: "idle" | "sending" | "success" | "failed";
  message: string;
};

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

export function Alerts(): JSX.Element {
  const { projectId } = useProjectContext();

  const [webhookSettings, setWebhookSettings] = useState<ProjectWebhookSettings | null>(null);
  const [webhookEnabledInput, setWebhookEnabledInput] = useState<boolean>(false);
  const [emailEnabledInput, setEmailEnabledInput] = useState<boolean>(false);
  const [webhookUrlInput, setWebhookUrlInput] = useState<string>("");
  const [webhookSecretInput, setWebhookSecretInput] = useState<string>("");
  const [webhookSaving, setWebhookSaving] = useState<boolean>(false);
  const [webhookTesting, setWebhookTesting] = useState<boolean>(false);
  const [webhookError, setWebhookError] = useState<string | null>(null);
  const [testStatus, setTestStatus] = useState<TestStatus>({ kind: "idle", message: "" });
  const [protectEnabled, setProtectEnabled] = useState<boolean>(false);
  const accountEmail = useMemo(() => {
    const raw = getAuthItem(frontendConfig.authUserStorageKey);
    if (!raw) {
      return "your account email";
    }
    try {
      const parsed = JSON.parse(raw) as { email?: string };
      return parsed.email || "your account email";
    } catch {
      return "your account email";
    }
  }, []);

  const reloadWebhookSettings = async (preserveInputs = false): Promise<void> => {
    if (!projectId) {
      return;
    }
    const [settings, protectSettings] = await Promise.all([fetchProjectWebhook(projectId), fetchProjectProtect(projectId)]);
    setWebhookSettings(settings);
    setProtectEnabled(Boolean(protectSettings.protect_enabled));
    if (!preserveInputs) {
      setWebhookEnabledInput(settings.enabled);
      setEmailEnabledInput(Boolean(settings.email_enabled));
      setWebhookUrlInput(settings.url ?? "");
      setWebhookSecretInput("");
    }
  };

  useEffect(() => {
    if (!projectId) {
      setWebhookSettings(null);
      setWebhookError(null);
      setProtectEnabled(false);
      return;
    }

    let cancelled = false;
    const loadSettings = async (): Promise<void> => {
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
        setWebhookError(null);
      } catch (error) {
        if (!cancelled) {
          setWebhookSettings(null);
          setWebhookError(error instanceof Error ? error.message : "Failed to load webhook settings.");
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
  const controlsDisabled = !projectId || webhookSaving || webhookTesting;
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
      || webhookSecretInput.trim().length > 0
    );
  }, [webhookSettings, webhookEnabledInput, emailEnabledInput, webhookUrlInput, webhookSecretInput]);

  const discardUnsavedChanges = (): void => {
    if (!webhookSettings) {
      return;
    }
    setWebhookEnabledInput(Boolean(webhookSettings.enabled));
    setEmailEnabledInput(Boolean(webhookSettings.email_enabled));
    setWebhookUrlInput(webhookSettings.url ?? "");
    setWebhookSecretInput("");
    setWebhookError(null);
    setTestStatus({ kind: "idle", message: "" });
  };

  const saveWebhookSettings = async (): Promise<void> => {
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
        secret: webhookSecretInput.trim() || null,
      });
      await reloadWebhookSettings();
    } catch (error) {
      setWebhookError(error instanceof Error ? error.message : "Failed to save webhook settings.");
      throw error;
    } finally {
      setWebhookSaving(false);
    }
  };

  const onSaveWebhookSettings = async (): Promise<void> => {
    setTestStatus({ kind: "idle", message: "" });
    await saveWebhookSettings();
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
    setTestStatus({ kind: "sending", message: "Saving settings..." });
    setWebhookTesting(true);
    setWebhookError(null);
    try {
      await saveWebhookSettings();
      setTestStatus({ kind: "sending", message: "Sending test..." });
      await testProjectWebhook(projectId);
      setTestStatus({ kind: "success", message: "Success (queued)." });
      window.setTimeout(() => {
        void reloadWebhookSettings(true);
      }, 700);
    } catch (error) {
      if (error instanceof ApiError) {
        setTestStatus({
          kind: "failed",
          message: `Failed (HTTP ${error.status}).`,
        });
      } else {
        setTestStatus({ kind: "failed", message: "Failed." });
      }
      setWebhookError(error instanceof Error ? error.message : "Failed to queue webhook test.");
    } finally {
      setWebhookTesting(false);
    }
  };

  if (!projectId) {
    return (
      <main className="dashboard">
        <div className="dashboard-content page-stack">
          <h1 className="page-title">Alerts</h1>
          <section className="empty">Select a project to configure webhook alerts.</section>
        </div>
      </main>
    );
  }

  return (
    <main className="dashboard">
      <div className="dashboard-content page-stack alerts-page-stack">
        <section>
          <h1 className="page-title">Alerts</h1>
          <p className="page-subtitle">Configure notification routes for incidents and enforcement events</p>
        </section>

        <div className="alerts-cards-row">
          <Card className="form-card card--form alerts-card">
            <h2 className="section-title">Email</h2>
            <p className="alerts-helper">Send notifications to your account email</p>
            <FormColumn>
              <div className="alerts-grid">
                <div className="form-field alerts-enabled">
                  <label htmlFor="alerts-email-enabled-toggle" className="alerts-toggle-row">
                    <span className="toggle-switch">
                      <input
                        id="alerts-email-enabled-toggle"
                        type="checkbox"
                        checked={emailEnabledInput}
                        disabled={controlsDisabled}
                        onChange={(event) => setEmailEnabledInput(event.target.checked)}
                        role="switch"
                      />
                      <span className="toggle-switch-track" aria-hidden="true" />
                    </span>
                    <span>{emailEnabledInput ? "On" : "Off"}</span>
                  </label>
                </div>
                <p className="alerts-destination">
                  <span className="alerts-destination-label">To:</span>{" "}
                  <span className="alerts-destination-email">{accountEmail}</span>
                </p>
                <div className="modal-actions form-actions">
                  <button
                    type="button"
                    className="modal-button modal-primary action-btn"
                    onClick={() => void onSaveWebhookSettings()}
                    disabled={controlsDisabled}
                  >
                    {webhookSaving ? "Saving..." : "Save"}
                  </button>
                </div>
              </div>
            </FormColumn>
          </Card>

          <Card className="form-card card--form alerts-card">
            <h2 className="section-title">Webhook</h2>
            <p className="alerts-helper">
              {protectEnabled
                ? "Deliver notifications to your webhook endpoint"
                : "Configure now. Delivery starts when Protect is enabled"}
            </p>
            <FormColumn testId="alerts-form-column">
              <div className={`alerts-grid ${controlsDisabled ? "is-disabled" : ""}`}>
                <div className="form-field alerts-enabled">
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
                    <span>{webhookEnabledInput ? "On" : "Off"}</span>
                  </label>
                </div>
                {!protectEnabled && webhookEnabledInput ? (
                  <p className="alerts-pending-status">Configured — will start delivering when you enable Protect</p>
                ) : null}
                <div className="form-field alerts-url alerts-webhook-field">
                  <label htmlFor="webhook-url" title="HTTPS endpoint that receives RHEONIC webhook events.">
                    Webhook URL
                  </label>
                  <input
                    id="webhook-url"
                    className={`text-input alerts-webhook-input ${webhookError ? "input-error" : ""}`}
                    type="url"
                    placeholder="https://..."
                    value={webhookUrlInput}
                    onChange={(event) => setWebhookUrlInput(event.target.value)}
                    disabled={controlsDisabled}
                  />
                </div>
                <div className="form-field alerts-webhook-field">
                  <label htmlFor="webhook-secret" title="Optional secret used by your receiver for signature verification.">
                    Secret (optional)
                  </label>
                  <input
                    id="webhook-secret"
                    className="text-input alerts-webhook-input"
                    type="password"
                    placeholder={webhookSettings?.has_secret ? "•••••••• (leave blank to keep)" : "optional"}
                    value={webhookSecretInput}
                    onChange={(event) => setWebhookSecretInput(event.target.value)}
                    disabled={controlsDisabled}
                  />
                </div>
                <p className="form-error-slot alerts-error-slot">{webhookError ?? "\u00A0"}</p>
                <p className="alerts-status">
                  Last delivery:
                  {" "}
                  <span className={webhookSettings?.last_status === "failed" ? "alerts-failed" : "alerts-success"}>
                    {webhookSettings?.last_status ? webhookSettings.last_status : "—"}
                  </span>
                  {" "}
                  <span>{formatDateTime(webhookSettings?.last_at ?? null)}</span>
                </p>
                <div className="modal-actions form-actions">
                  <button
                    type="button"
                    className="modal-button action-btn"
                    onClick={() => void onTestWebhook()}
                    disabled={!canTestWebhook}
                  >
                    {webhookTesting ? "Testing..." : "Test webhook"}
                  </button>
                  <button
                    type="button"
                    className="modal-button modal-primary action-btn"
                    onClick={() => void onSaveWebhookSettings()}
                    disabled={controlsDisabled}
                  >
                    {webhookSaving ? "Saving..." : "Save"}
                  </button>
                </div>
                {testStatus.kind !== "idle" ? (
                  <p
                    className={`alerts-test-status ${testStatus.kind === "failed" ? "failed" : testStatus.kind === "success" ? "success" : ""}`}
                  >
                    {testStatus.message}
                  </p>
                ) : null}
              </div>
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
