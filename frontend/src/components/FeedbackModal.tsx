import { useEffect, useState } from "react";

import { fetchProjectProtect, sendFeedback } from "../api/client";
import { frontendConfig } from "../config";
import { useProjectContext } from "../context/ProjectContext";
import { showAppToast } from "./AppToastHost";

interface FeedbackModalProps {
  open: boolean;
  onClose: () => void;
}

export function FeedbackModal({ open, onClose }: FeedbackModalProps): JSX.Element | null {
  const { projectId } = useProjectContext();
  const [message, setMessage] = useState<string>("");
  const [email, setEmail] = useState<string>("");
  const [sending, setSending] = useState<boolean>(false);
  const [mode, setMode] = useState<"observe" | "protect">("observe");

  useEffect(() => {
    if (!open) {
      return;
    }
    setMessage("");
    setEmail("");
    if (!projectId) {
      setMode("observe");
      return;
    }
    let cancelled = false;
    const loadMode = async (): Promise<void> => {
      try {
        const protect = await fetchProjectProtect(projectId);
        if (!cancelled) {
          setMode(protect.protect_enabled ? "protect" : "observe");
        }
      } catch {
        if (!cancelled) {
          setMode("observe");
        }
      }
    };
    void loadMode();
    return () => {
      cancelled = true;
    };
  }, [open, projectId]);

  if (!open) {
    return null;
  }

  const onSend = async (): Promise<void> => {
    const trimmed = message.trim();
    if (!trimmed) {
      return;
    }
    setSending(true);
    try {
      await sendFeedback({
        message: trimmed,
        email: email.trim() || null,
        project_id: projectId ?? null,
        page: window.location.pathname,
        mode,
        timestamp: new Date().toISOString(),
        app_version: frontendConfig.appVersion || null,
      });
      showAppToast("Feedback sent. Thank you.");
      onClose();
    } catch {
      showAppToast("Failed to send feedback. Try again.");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="feedback-modal-title">
      <div className="modal">
        <h2 id="feedback-modal-title" className="section-title">
          Send feedback
        </h2>
        <p className="subtle">
          Tell us what&apos;s confusing, broken, or missing.
          <br />
          Your feedback helps improve Rheonic during beta.
        </p>
        <div className="form-field">
          <label htmlFor="feedback-message">Message</label>
          <textarea
            id="feedback-message"
            className="text-input feedback-textarea"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Write your feedback"
          />
        </div>
        <div className="form-field">
          <label htmlFor="feedback-email">Email (optional)</label>
          <input
            id="feedback-email"
            className="text-input"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
          />
        </div>
        <div className="modal-actions">
          <button type="button" className="modal-button" onClick={onClose} disabled={sending}>
            Cancel
          </button>
          <button
            type="button"
            className="modal-button modal-primary"
            onClick={() => void onSend()}
            disabled={sending || !message.trim()}
          >
            {sending ? "Sending..." : "Send feedback"}
          </button>
        </div>
      </div>
    </div>
  );
}
