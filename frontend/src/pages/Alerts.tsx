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
import { useProjectContext } from "../context/ProjectContext";

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
  const [webhookUrlInput, setWebhookUrlInput] = useState<string>("");
  const [webhookSecretInput, setWebhookSecretInput] = useState<string>("");
  const [webhookSaving, setWebhookSaving] = useState<boolean>(false);
  const [webhookTesting, setWebhookTesting] = useState<boolean>(false);
  const [webhookError, setWebhookError] = useState<string | null>(null);
  const [testStatus, setTestStatus] = useState<TestStatus>({ kind: "idle", message: "" });
  const [protectEnabled, setProtectEnabled] = useState<boolean>(false);

  const reloadWebhookSettings = async (preserveInputs = false): Promise<void> => {
    if (!projectId) {
      return;
    }
    const [settings, protectSettings] = await Promise.all([fetchProjectWebhook(projectId), fetchProjectProtect(projectId)]);
    setWebhookSettings(settings);
    setProtectEnabled(Boolean(protectSettings.protect_enabled));
    if (!preserveInputs) {
      setWebhookEnabledInput(settings.enabled);
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
      && protectEnabled
      && webhookEnabledInput
      && webhookUrlInput.trim().length > 0
      && !webhookTesting
      && !webhookSaving,
    [projectId, protectEnabled, webhookEnabledInput, webhookUrlInput, webhookTesting, webhookSaving],
  );
  const controlsDisabled = !projectId || webhookSaving || webhookTesting || !protectEnabled;

  const saveWebhookSettings = async (): Promise<void> => {
    if (!projectId || !protectEnabled) {
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
      throw error;
    } finally {
      setWebhookSaving(false);
    }
  };

  const onSaveWebhookSettings = async (): Promise<void> => {
    setTestStatus({ kind: "idle", message: "" });
    await saveWebhookSettings();
  };

  const onTestWebhook = async (): Promise<void> => {
    if (!projectId || !protectEnabled) {
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
      <div className="dashboard-content page-stack">
        <section>
          <h1 className="page-title">Alerts</h1>
          <p className="page-subtitle">Configure webhook notifications for incidents and events</p>
        </section>

        <Card className="form-card card--form">
          <h2 className="section-title">Webhook</h2>
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
              <div className="form-field alerts-url">
                <label htmlFor="webhook-url" title="HTTPS endpoint that receives RHEONIC webhook events.">
                  Webhook URL
                </label>
                <input
                  id="webhook-url"
                  className={`text-input ${webhookError ? "input-error" : ""}`}
                  type="url"
                  placeholder="https://..."
                  value={webhookUrlInput}
                  onChange={(event) => setWebhookUrlInput(event.target.value)}
                  disabled={controlsDisabled}
                />
              </div>
              <div className="form-field">
                <label htmlFor="webhook-secret" title="Optional secret used by your receiver for signature verification.">
                  Secret (optional)
                </label>
                <input
                  id="webhook-secret"
                  className="text-input"
                  type="password"
                  placeholder={webhookSettings?.has_secret ? "•••••••• (leave blank to keep)" : "optional"}
                  value={webhookSecretInput}
                  onChange={(event) => setWebhookSecretInput(event.target.value)}
                  disabled={controlsDisabled}
                />
              </div>
              <p className="form-error-slot">{webhookError ?? "\u00A0"}</p>
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
    </main>
  );
}
