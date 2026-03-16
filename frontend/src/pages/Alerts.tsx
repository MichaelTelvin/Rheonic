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

const TEMPLATE_PLACEHOLDERS = [
  "event",
  "project_id",
  "incident_id",
  "incident_type",
  "provider",
  "model",
  "environment",
  "sent_at",
  "resolved_at",
  "resolved_by",
  "reason",
  "requests_60s",
  "tokens_60s",
  "req_cap",
  "tok_cap",
  "destination",
  "status",
  "attempts",
  "max_attempts",
  "last_error_code",
  "last_error_message",
] as const;

const LOCKED_METADATA_KEY = "rheonic";
const DEFAULT_MESSAGE_TEXT = "Rheonic {{event}} for {{project_id}}: {{incident_type}}";
const DEFAULT_CUSTOM_PROPERTIES = "{}";

const PREVIEW_EVENTS = [
  "incident.warn",
  "incident.block",
  "incident.resolved",
  "policy_gap.detected",
  "webhook.delivery_failed",
  "webhook.test",
] as const;

const PLACEHOLDER_PATTERN = /\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g;

function renderTemplateNode(node: unknown, context: Record<string, string>): unknown {
  if (Array.isArray(node)) {
    return node.map((item) => renderTemplateNode(item, context));
  }
  if (node && typeof node === "object") {
    return Object.fromEntries(
      Object.entries(node as Record<string, unknown>).map(([key, value]) => [key, renderTemplateNode(value, context)]),
    );
  }
  if (typeof node === "string") {
    return node.replace(PLACEHOLDER_PATTERN, (_, token: string) => context[token] ?? "");
  }
  return node;
}

function parsePayloadTemplateForEditor(value: string | null): { messageText: string; customPropertiesText: string } {
  if (!value) {
    return {
      messageText: DEFAULT_MESSAGE_TEXT,
      customPropertiesText: DEFAULT_CUSTOM_PROPERTIES,
    };
  }
  try {
    const parsed = JSON.parse(value) as Record<string, unknown>;
    const editable = { ...parsed };
    delete editable[LOCKED_METADATA_KEY];
    const messageText = typeof editable.text === "string" ? editable.text : DEFAULT_MESSAGE_TEXT;
    delete editable.text;
    return {
      messageText,
      customPropertiesText: Object.keys(editable).length > 0 ? JSON.stringify(editable, null, 2) : DEFAULT_CUSTOM_PROPERTIES,
    };
  } catch {
    return {
      messageText: DEFAULT_MESSAGE_TEXT,
      customPropertiesText: DEFAULT_CUSTOM_PROPERTIES,
    };
  }
}

function buildLockedMetadataTemplate(): Record<string, string> {
  return Object.fromEntries(TEMPLATE_PLACEHOLDERS.map((field) => [field, `{{${field}}}`]));
}

function parseCustomProperties(source: string): Record<string, unknown> {
  const trimmed = source.trim();
  if (!trimmed) {
    return {};
  }
  const parsed = JSON.parse(trimmed) as unknown;
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("Custom properties must be a JSON object.");
  }
  const record = { ...(parsed as Record<string, unknown>) };
  delete record[LOCKED_METADATA_KEY];
  delete record.text;
  return record;
}

function buildPayloadTemplateJson(messageText: string, customPropertiesText: string): string {
  const customProperties = parseCustomProperties(customPropertiesText);
  const template: Record<string, unknown> = {
    ...customProperties,
    [LOCKED_METADATA_KEY]: buildLockedMetadataTemplate(),
  };
  if (messageText.trim()) {
    template.text = messageText.trim();
  }
  return JSON.stringify(template);
}

function renderCompactPayloadPreview(
  messageText: string,
  customPropertiesText: string,
  eventType: typeof PREVIEW_EVENTS[number],
): string {
  const template = JSON.parse(buildPayloadTemplateJson(messageText, customPropertiesText)) as Record<string, unknown>;
  const context = sampleWebhookContext(eventType);
  const rendered = renderTemplateNode(template, context);
  const record = rendered as Record<string, unknown>;
  const compactPreview: Record<string, unknown> = {};
  if (typeof record.text === "string" && record.text.trim()) {
    compactPreview.text = record.text;
  }
  for (const [key, value] of Object.entries(record)) {
    if (key === "text" || key === LOCKED_METADATA_KEY) {
      continue;
    }
    compactPreview[key] = value;
  }
  compactPreview[LOCKED_METADATA_KEY] = "{ protected Rheonic metadata added automatically }";
  return JSON.stringify(compactPreview, null, 2);
}

function sampleWebhookContext(eventType: typeof PREVIEW_EVENTS[number]): Record<string, string> {
  const base = {
    event: eventType,
    project_id: "proj_123",
    incident_id: "inc_456",
    incident_type: "retry_storm",
    provider: "openai",
    model: "gpt-4o-mini",
    environment: "staging",
    sent_at: "Mar 16, 2026 12:30 UTC",
    resolved_at: "Mar 16, 2026 12:37 UTC",
    resolved_by: "user@example.com",
    reason: "retry_storm",
    requests_60s: "5",
    tokens_60s: "250",
    req_cap: "400",
    tok_cap: "1700",
    destination: "https://hooks.example.test/rheonic",
    status: "dead",
    attempts: "3",
    max_attempts: "3",
    last_error_code: "webhook_http_error",
    last_error_message: "HTTP 404",
  };
  if (eventType === "incident.block") {
    return { ...base, incident_type: "cap_breach", reason: "tok_cap_breach", tokens_60s: "4000" };
  }
  if (eventType === "incident.resolved") {
    return { ...base, incident_type: "cap_breach", reason: "cap_breach" };
  }
  if (eventType === "policy_gap.detected") {
    return { ...base, incident_id: "", incident_type: "", reason: "", model: "claude-3-5-sonnet" };
  }
  if (eventType === "webhook.delivery_failed") {
    return { ...base, incident_id: "", incident_type: "", provider: "", model: "", environment: "" };
  }
  if (eventType === "webhook.test") {
    return { ...base, incident_id: "", incident_type: "", reason: "", provider: "", model: "" };
  }
  return base;
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
  const [payloadTemplateEnabledInput, setPayloadTemplateEnabledInput] = useState<boolean>(false);
  const [payloadMessageTextInput, setPayloadMessageTextInput] = useState<string>(DEFAULT_MESSAGE_TEXT);
  const [payloadCustomPropertiesInput, setPayloadCustomPropertiesInput] = useState<string>(DEFAULT_CUSTOM_PROPERTIES);
  const [payloadPreviewEvent, setPayloadPreviewEvent] = useState<typeof PREVIEW_EVENTS[number]>("incident.warn");
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
        setPayloadTemplateEnabledInput(Boolean(settings.payload_template_json));
        const parsedTemplate = parsePayloadTemplateForEditor(settings.payload_template_json);
        setPayloadMessageTextInput(parsedTemplate.messageText);
        setPayloadCustomPropertiesInput(parsedTemplate.customPropertiesText);
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
        setPayloadTemplateEnabledInput(Boolean(settings.payload_template_json));
        const parsedTemplate = parsePayloadTemplateForEditor(settings.payload_template_json);
        setPayloadMessageTextInput(parsedTemplate.messageText);
        setPayloadCustomPropertiesInput(parsedTemplate.customPropertiesText);
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
      || payloadTemplateEnabledInput !== Boolean(webhookSettings.payload_template_json)
      || (payloadTemplateEnabledInput
        && (
          payloadMessageTextInput !== savedTemplate.messageText
          || payloadCustomPropertiesInput !== savedTemplate.customPropertiesText
        ))
    );
  }, [
    webhookSettings,
    webhookEnabledInput,
    emailEnabledInput,
    webhookUrlInput,
    webhookSecretInput,
    payloadTemplateEnabledInput,
    payloadMessageTextInput,
    payloadCustomPropertiesInput,
  ]);

  const payloadTemplateError = useMemo(() => {
    if (!payloadTemplateEnabledInput) {
      return null;
    }
    try {
      parseCustomProperties(payloadCustomPropertiesInput);
      return null;
    } catch {
      return "Custom properties must be valid JSON object fields.";
    }
  }, [payloadTemplateEnabledInput, payloadCustomPropertiesInput]);

  const payloadTemplatePreview = useMemo(() => {
    if (!payloadTemplateEnabledInput) {
      return "";
    }
    if (payloadTemplateError) {
      return "";
    }
    try {
      return renderCompactPayloadPreview(payloadMessageTextInput, payloadCustomPropertiesInput, payloadPreviewEvent);
    } catch {
      return "";
    }
  }, [
    payloadTemplateEnabledInput,
    payloadTemplateError,
    payloadMessageTextInput,
    payloadCustomPropertiesInput,
    payloadPreviewEvent,
  ]);

  const discardUnsavedChanges = (): void => {
    if (!webhookSettings) {
      return;
    }
    setWebhookEnabledInput(Boolean(webhookSettings.enabled));
    setEmailEnabledInput(Boolean(webhookSettings.email_enabled));
    setWebhookUrlInput(webhookSettings.url ?? "");
    setWebhookSecretInput("");
    setPayloadTemplateEnabledInput(Boolean(webhookSettings.payload_template_json));
    const parsedTemplate = parsePayloadTemplateForEditor(webhookSettings.payload_template_json);
    setPayloadMessageTextInput(parsedTemplate.messageText);
    setPayloadCustomPropertiesInput(parsedTemplate.customPropertiesText);
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
        payload_template_json: payloadTemplateEnabledInput
          ? buildPayloadTemplateJson(payloadMessageTextInput, payloadCustomPropertiesInput)
          : null,
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
      await saveWebhookSettings(false);
      await testProjectWebhook(projectId, {
        payload_template_json: payloadTemplateEnabledInput
          ? buildPayloadTemplateJson(payloadMessageTextInput, payloadCustomPropertiesInput)
          : null,
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
      <main className="dashboard">
        <div className="dashboard-content page-stack">
          <h1 className="page-title">Alerts</h1>
          <section className="empty">Select a project to configure webhook alerts.</section>
        </div>
      </main>
    );
  }

  if (loadingSettings && webhookSettings === null) {
    return (
      <main className="dashboard">
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
    <main className="dashboard">
      <div className="dashboard-content page-stack alerts-page-stack">
        <section>
          <h1 className="page-title">Alerts</h1>
          <p className="page-subtitle">Configure protect lifecycle alert routes for email and webhook delivery</p>
        </section>

        <Card className="form-card alerts-main-card">
          <div className="alerts-main-grid">
            <section className="alerts-section alerts-section-email">
              <div className="alerts-section-head">
                <h2 className="section-title">Email</h2>
                <p className="alerts-helper">Send protect lifecycle alerts to your account email.</p>
              </div>
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
                    <span className="alerts-destination-label">Recipient</span>
                    <span className="alerts-destination-email">{accountEmail}</span>
                  </p>
                </div>
              </FormColumn>
            </section>

            <section className="alerts-section alerts-section-webhook">
              <div className="alerts-section-head">
                <h2 className="section-title">Webhook</h2>
                <p className="alerts-helper">
                  {protectEnabled
                    ? "Deliver the same protect lifecycle alerts to your webhook endpoint."
                    : "Configure now. Delivery starts when Protect is enabled."}
                </p>
              </div>
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
                    <p className="alerts-pending-status">Configured - will start delivering when you enable Protect</p>
                  ) : null}
                  <div className="form-field alerts-url alerts-webhook-field">
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
                      disabled={controlsDisabled || webhookTesting}
                    />
                  </div>
                  <div className="form-field alerts-webhook-field">
                    <label htmlFor="alerts-custom-payload-toggle" className="alerts-toggle-row">
                      <span className="toggle-switch">
                        <input
                          id="alerts-custom-payload-toggle"
                          type="checkbox"
                          checked={payloadTemplateEnabledInput}
                          disabled={controlsDisabled || webhookTesting}
                          onChange={(event) => setPayloadTemplateEnabledInput(event.target.checked)}
                          role="switch"
                        />
                        <span className="toggle-switch-track" aria-hidden="true" />
                      </span>
                      <span>Use custom payload</span>
                    </label>
                  </div>
                  <p className="form-error-slot alerts-error-slot">{webhookError ?? payloadTemplateError ?? "\u00A0"}</p>
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
                </div>
              </FormColumn>
            </section>
          </div>

          {payloadTemplateEnabledInput ? (
            <section className="alerts-inline-builder">
              <div className="alerts-editor-header">
                <div>
                  <h2 className="section-title">Custom Payload</h2>
                  <p className="alerts-helper">
                    Add your own text and top-level provider fields. Protected Rheonic metadata is attached automatically.
                  </p>
                </div>
              </div>
              <div className={`alerts-editor-grid ${controlsDisabled ? "is-disabled" : ""}`}>
                <div className="alerts-editor-column">
                <div className="form-field">
                  <label htmlFor="payload-message-text">Message text</label>
                  <textarea
                    id="payload-message-text"
                    className="text-input alerts-template-textarea"
                    rows={4}
                    value={payloadMessageTextInput}
                    onChange={(event) => setPayloadMessageTextInput(event.target.value)}
                    disabled={controlsDisabled || webhookTesting}
                    placeholder="Rheonic {{event}} for {{project_id}}: {{incident_type}}"
                  />
                  <p className="alerts-helper">
                    Optional. Use placeholders like <code>{"{{incident_type}}"}</code> or <code>{"{{provider}}"}</code>.
                  </p>
                </div>
                <div className="form-field">
                  <label htmlFor="payload-custom-properties">Extra fields (JSON object)</label>
                  <textarea
                    id="payload-custom-properties"
                    className={`text-input alerts-template-textarea ${payloadTemplateError ? "input-error" : ""}`}
                    rows={8}
                    value={payloadCustomPropertiesInput}
                    onChange={(event) => setPayloadCustomPropertiesInput(event.target.value)}
                    disabled={controlsDisabled || webhookTesting}
                    placeholder={"{\n  \"chat_id\": \"123456789\",\n  \"parse_mode\": \"Markdown\"\n}"}
                  />
                  <p className="alerts-helper">
                    Put provider-specific top-level fields here, for example <code>chat_id</code>, <code>thread_id</code>,
                    or <code>parse_mode</code>.
                  </p>
                </div>
              </div>
              <div className="alerts-editor-column">
                <div className="form-field">
                  <label htmlFor="payload-preview-event">Preview event</label>
                  <select
                    id="payload-preview-event"
                    className="text-input alerts-webhook-input"
                    value={payloadPreviewEvent}
                    onChange={(event) => setPayloadPreviewEvent(event.target.value as typeof PREVIEW_EVENTS[number])}
                    disabled={controlsDisabled || webhookTesting}
                  >
                    {PREVIEW_EVENTS.map((eventName) => (
                      <option key={eventName} value={eventName}>
                        {eventName}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-field">
                  <label htmlFor="payload-preview">Compact preview</label>
                  <textarea
                    id="payload-preview"
                    className="text-input alerts-template-textarea"
                    rows={12}
                    value={payloadTemplatePreview}
                    readOnly
                  />
                  <p className="alerts-helper">
                    Your custom fields are shown directly. The protected <code>rheonic</code> object is attached automatically at send time.
                  </p>
                </div>
                <div className="form-field">
                  <p className="alerts-helper">Available placeholders: {TEMPLATE_PLACEHOLDERS.join(", ")}</p>
                </div>
              </div>
              </div>
            </section>
          ) : null}
        </Card>
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
