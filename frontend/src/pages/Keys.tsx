import { useEffect, useLayoutEffect, useState } from "react";

import { formatRelative } from "./dashboardUtils";
import { createKey, listKeys, revokeKey, rotateKey, type CreateKeyResponse, type IngestKeyItem } from "../api/client";
import { showAppToast } from "../components/AppToastHost";
import { Card } from "../components/Card";
import { FormColumn } from "../components/FormColumn";
import { frontendConfig } from "../config";
import { useProjectContext } from "../context/ProjectContext";

const NAME_REGEX = new RegExp(frontendConfig.dashboardNamePattern);
const NAME_MAX = frontendConfig.dashboardNameMaxLength;

type KeysCacheState = {
  keys: IngestKeyItem[];
};

function keysCacheKey(projectId: string): string {
  return `rheonic:keys:${projectId}`;
}

function readKeysCache(projectId: string | null): KeysCacheState | null {
  if (!projectId) {
    return null;
  }
  try {
    const raw = window.sessionStorage.getItem(keysCacheKey(projectId));
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<KeysCacheState>;
    return {
      keys: Array.isArray(parsed.keys) ? parsed.keys : [],
    };
  } catch {
    return null;
  }
}

export function Keys(): JSX.Element {
  const { projectId } = useProjectContext();
  const initialCache = readKeysCache(projectId);

  const [keys, setKeys] = useState<IngestKeyItem[]>(initialCache?.keys ?? []);
  const [loadingKeys, setLoadingKeys] = useState<boolean>(projectId ? initialCache === null : false);
  const [keysError, setKeysError] = useState<string | null>(null);
  const [newKeyName, setNewKeyName] = useState<string>("");
  const [creatingKey, setCreatingKey] = useState<boolean>(false);
  const [processingKeyId, setProcessingKeyId] = useState<string | null>(null);
  const [latestPlaintextKey, setLatestPlaintextKey] = useState<CreateKeyResponse | null>(null);
  const [, setCopiedAction] = useState<string | null>(null);
  const activeKeys = keys.filter((key) => key.status === "active");

  useLayoutEffect(() => {
    const cached = readKeysCache(projectId);
    setKeys(cached?.keys ?? []);
    setLoadingKeys(projectId ? cached === null : false);
    setKeysError(null);
  }, [projectId]);

  useEffect(() => {
    if (!projectId) {
      return undefined;
    }
    try {
      window.sessionStorage.setItem(
        keysCacheKey(projectId),
        JSON.stringify({
          keys,
        } satisfies KeysCacheState),
      );
    } catch {
      // Ignore cache write failures.
    }
    return undefined;
  }, [keys, projectId]);

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

  const reloadKeys = async (): Promise<void> => {
    if (!projectId) {
      setKeys([]);
      return;
    }
    const items = await listKeys(projectId);
    setKeys(items);
  };

  useEffect(() => {
    if (!projectId) {
      setKeys([]);
      setLoadingKeys(false);
      setKeysError(null);
      return undefined;
    }

    let cancelled = false;
    const cached = readKeysCache(projectId);
    setLoadingKeys(cached === null);
    setKeysError(null);

    const load = async (): Promise<void> => {
      try {
        const items = await listKeys(projectId);
        if (!cancelled) {
          setKeys(items);
        }
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

    void load();

    return () => {
      cancelled = true;
    };
  }, [projectId]);

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
      showAppToast("Key created");
    } catch (error) {
      setKeysError(error instanceof Error ? error.message : "Failed to create key.");
      showAppToast("Action failed. Try again");
    } finally {
      setCreatingKey(false);
    }
  };

  const onRevokeKey = async (keyId: string): Promise<void> => {
    setProcessingKeyId(keyId);
    setKeysError(null);
    try {
      await revokeKey(keyId);
      await reloadKeys();
      showAppToast("Key revoked");
    } catch (error) {
      setKeysError(error instanceof Error ? error.message : "Failed to revoke key.");
      showAppToast("Action failed. Try again");
    } finally {
      setProcessingKeyId(null);
    }
  };

  const onRotateKey = async (keyId: string): Promise<void> => {
    setProcessingKeyId(keyId);
    setKeysError(null);
    try {
      const rotated = await rotateKey(keyId);
      setLatestPlaintextKey(rotated);
      await reloadKeys();
      showAppToast("Key refreshed");
    } catch (error) {
      setKeysError(error instanceof Error ? error.message : "Failed to rotate key.");
      showAppToast("Action failed. Try again");
    } finally {
      setProcessingKeyId(null);
    }
  };

  const copyText = async (value: string, actionId: string): Promise<void> => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedAction(actionId);
      showAppToast("Copied to clipboard");
      window.setTimeout(() => {
        setCopiedAction((current) => (current === actionId ? null : current));
      }, 1200);
    } catch {
      setKeysError("Copy failed. Copy manually from the box.");
    }
  };

  if (!projectId) {
    return (
      <main className="dashboard">
        <div className="dashboard-content page-stack">
          <h1 className="page-title">Keys</h1>
          <section className="empty">Select a project to manage ingest keys.</section>
        </div>
      </main>
    );
  }

  return (
    <main className="dashboard">
      <div className="dashboard-content page-stack">
        <section>
          <h1 className="page-title">Keys</h1>
          <p className="page-subtitle">Manage API keys</p>
        </section>

        <Card className="form-card projects-shell-width">
          <h2 className="section-title">Create key</h2>
          <FormColumn testId="keys-form-column">
            <div className="form-field">
              <label htmlFor="new-key-name">Key label (environment)</label>
              <input
                id="new-key-name"
                className="text-input key-input"
                value={newKeyName}
                onChange={(event) => setNewKeyName(event.target.value)}
                placeholder="e.g. production"
                title="Example: prod, staging, dev"
              />
            </div>
            <p className="form-error-slot">{keysError ?? "\u00A0"}</p>
            <div className="modal-actions form-actions">
              <button
                type="button"
                className="modal-button modal-primary action-btn"
                onClick={() => void onCreateKey()}
                disabled={creatingKey}
              >
                {creatingKey ? "Creating..." : "Create key"}
              </button>
            </div>
          </FormColumn>
        </Card>

        {latestPlaintextKey ? (
          <Card className="card--table">
            <h2 className="section-title">New key (shown once)</h2>
            <div className="secret-box">
              <p className="warning-text">Copy this key now. It will not be visible again.</p>
              <pre>{latestPlaintextKey.key}</pre>
              <div className="secret-actions">
                <button
                  type="button"
                  className="modal-button"
                  onClick={() => void copyText(latestPlaintextKey.key, "key")}
                >
                  Copy key
                </button>
                <button
                  type="button"
                  className="modal-button"
                  onClick={() => void copyText(`RHEONIC_INGEST_KEY="${latestPlaintextKey.key}"`, "env")}
                >
                  Copy env var
                </button>
              </div>
            </div>
          </Card>
        ) : null}

        <Card className="card--table">
          <h2 className="section-title">Existing keys</h2>
          <div className={`keys-list ${loadingKeys ? "keys-list-loading" : ""}`}>
            <div className="key-row key-row-header">
              <span className="subtle">Label</span>
              <span className="subtle">Status</span>
              <span className="subtle">Last 4</span>
              <span className="subtle">Created</span>
              <span className="subtle key-actions-col table-actions-header">Actions</span>
            </div>
            {loadingKeys ? (
              <>
                <div className="key-row key-row-data key-row-placeholder">Loading keys...</div>
                <div className="key-row key-row-data key-row-placeholder" aria-hidden="true" />
                <div className="key-row key-row-data key-row-placeholder" aria-hidden="true" />
              </>
            ) : null}
            {!loadingKeys && activeKeys.length === 0 ? <p className="subtle">No keys yet.</p> : null}
            {activeKeys.map((key) => (
              <div className="key-row key-row-data" key={key.id}>
                <span className="key-name">{key.name}</span>
                <span className={`badge ${key.status === "active" ? "low" : "high"}`}>{key.status}</span>
                <span className="subtle mono">{key.last4 ?? "----"}</span>
                <span className="subtle" title={key.created_at}>
                  {formatRelative(key.created_at)}
                </span>
                <div className="key-actions">
                  <button
                    type="button"
                    className="modal-button key-action-btn action-btn"
                    onClick={() => void onRotateKey(key.id)}
                    disabled={processingKeyId === key.id}
                  >
                    Rotate
                  </button>
                  <button
                    type="button"
                    className="modal-button key-action-btn action-btn key-action-danger"
                    onClick={() => void onRevokeKey(key.id)}
                    disabled={processingKeyId === key.id}
                  >
                    Revoke
                  </button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </main>
  );
}
