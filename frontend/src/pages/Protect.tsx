import { useEffect, useState } from "react";

import { fetchProjectProtect, updateProjectProtect, type ProjectProtectSettings } from "../api/client";
import { Card } from "../components/Card";
import { FormColumn } from "../components/FormColumn";
import { InfoTooltip } from "../components/InfoTooltip";
import { frontendConfig } from "../config";
import { useProjectContext } from "../context/ProjectContext";

export function Protect(): JSX.Element {
  const { projectId } = useProjectContext();

  const [protectSettings, setProtectSettings] = useState<ProjectProtectSettings | null>(null);
  const [savingProtect, setSavingProtect] = useState<boolean>(false);
  const [protectError, setProtectError] = useState<string | null>(null);
  const [protectEnabledInput, setProtectEnabledInput] = useState<boolean>(false);
  const [protectMaxReqInput, setProtectMaxReqInput] = useState<string>("");
  const [protectMaxTokInput, setProtectMaxTokInput] = useState<string>("");
  const [protectFailModeInput, setProtectFailModeInput] = useState<"open" | "closed">("open");
  const [applyClampInput, setApplyClampInput] = useState<boolean>(false);
  const failModeDisabled = !protectEnabledInput;
  const sanitizeDigits = (value: string): string => value.replace(/\D+/g, "");

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
        apply_clamp: applyClampInput,
        protect_max_req_per_min,
        protect_max_tok_per_min,
        protect_decision_timeout_ms:
          protectSettings?.protect_decision_timeout_ms ?? frontendConfig.protectDefaultDecisionTimeoutMs,
      });
      setProtectSettings(updated);
      setProtectEnabledInput(Boolean(updated.protect_enabled));
      setApplyClampInput(Boolean(updated.apply_clamp));
      window.dispatchEvent(
        new CustomEvent("rheonic:protect-mode-updated", {
          detail: { projectId, protect_enabled: Boolean(updated.protect_enabled) },
        }),
      );
    } catch (error) {
      setProtectError(error instanceof Error ? error.message : "Failed to save protect settings.");
    } finally {
      setSavingProtect(false);
    }
  };

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
                    setProtectEnabledInput(event.target.value === "protect");
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
      </div>
    </main>
  );
}
