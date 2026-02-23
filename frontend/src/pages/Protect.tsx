import { useEffect, useState } from "react";

import { fetchProjectProtect, updateProjectProtect, type ProjectProtectSettings } from "../api/client";
import { Card } from "../components/Card";
import { FormColumn } from "../components/FormColumn";
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
        protect_max_req_per_min,
        protect_max_tok_per_min,
        protect_decision_timeout_ms:
          protectSettings?.protect_decision_timeout_ms ?? frontendConfig.protectDefaultDecisionTimeoutMs,
      });
      setProtectSettings(updated);
      setProtectEnabledInput(Boolean(updated.protect_enabled));
      window.dispatchEvent(
        new CustomEvent("llmtbg:protect-mode-updated", {
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
          <h1 className="page-title">Protect</h1>
          <section className="empty">Select a project to configure protection rules.</section>
        </div>
      </main>
    );
  }

  return (
    <main className="dashboard">
      <div className="dashboard-content page-stack">
        <section>
          <h1 className="page-title">Protection</h1>
          <p className="page-subtitle">Enable or disable protection and configure limits</p>
        </section>

        <Card className="form-card card--form">
          <h2 className="section-title">Protect configuration</h2>
          <FormColumn testId="protect-form-column">
            <div className="form-field protect-mode">
              <label htmlFor="protect-mode-select">Mode</label>
              <select
                id="protect-mode-select"
                value={protectEnabledInput ? "protect" : "observe"}
                onChange={(event) => setProtectEnabledInput(event.target.value === "protect")}
                title="Observe = telemetry only, Protect = preflight decisions enforced."
              >
                <option value="observe">Observe</option>
                <option value="protect">Protect</option>
              </select>
            </div>

            <div className="form-field protect-req">
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
            </div>

            <div className="form-field">
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
            </div>

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
          </FormColumn>
        </Card>
      </div>
    </main>
  );
}
