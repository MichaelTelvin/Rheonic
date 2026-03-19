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
  const [reportType, setReportType] = useState<"feedback" | "bug">("bug");
  const [message, setMessage] = useState<string>("");
  const [email, setEmail] = useState<string>("");
  const [screenshotName, setScreenshotName] = useState<string>("");
  const [screenshotContentType, setScreenshotContentType] = useState<string>("");
  const [screenshotBase64, setScreenshotBase64] = useState<string>("");
  const [sending, setSending] = useState<boolean>(false);
  const [mode, setMode] = useState<"observe" | "protect">("observe");

  useEffect(() => {
    if (!open) {
      return;
    }
    setReportType("bug");
    setMessage("");
    setEmail("");
    setScreenshotName("");
    setScreenshotContentType("");
    setScreenshotBase64("");
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
        report_type: reportType,
        message: trimmed,
        email: email.trim() || null,
        screenshot_name: screenshotName || null,
        screenshot_content_type: screenshotContentType || null,
        screenshot_base64: screenshotBase64 || null,
        project_id: projectId ?? null,
        page: window.location.pathname,
        mode,
        timestamp: new Date().toISOString(),
        app_version: frontendConfig.appVersion || null,
      });
      showAppToast("Report sent. Thank you.");
      onClose();
    } catch {
      showAppToast("Failed to send report. Try again.");
    } finally {
      setSending(false);
    }
  };

  const onSelectScreenshot = async (file: File | null): Promise<void> => {
    if (!file) {
      setScreenshotName("");
      setScreenshotContentType("");
      setScreenshotBase64("");
      return;
    }
    if (!file.type.startsWith("image/")) {
      showAppToast("Screenshot must be an image.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      showAppToast("Screenshot must be 5 MB or smaller.");
      return;
    }
    try {
      const encoded = await readFileAsBase64(file);
      setScreenshotName(file.name);
      setScreenshotContentType(file.type || "image/png");
      setScreenshotBase64(encoded);
    } catch {
      showAppToast("Failed to read screenshot. Try again.");
    }
  };

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="feedback-modal-title">
      <div className="modal">
        <h2 id="feedback-modal-title" className="section-title">
          Report a bug or share feedback
        </h2>
        <p className="subtle">
          Tell us what&apos;s broken, confusing, or missing.
          <br />
          We&apos;ll include your account and current project context to help triage it.
        </p>
        <div className="form-field">
          <label htmlFor="feedback-type">Type</label>
          <select
            id="feedback-type"
            className="text-input"
            value={reportType}
            onChange={(event) => setReportType(event.target.value === "feedback" ? "feedback" : "bug")}
          >
            <option value="bug">Bug report</option>
            <option value="feedback">Product feedback</option>
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="feedback-message">Message</label>
          <textarea
            id="feedback-message"
            className="text-input feedback-textarea"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder={reportType === "bug" ? "What happened? What did you expect?" : "What should we improve?"}
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
        <div className="form-field">
          <label htmlFor="feedback-screenshot">Screenshot (optional)</label>
          <input
            id="feedback-screenshot"
            className="text-input"
            type="file"
            accept="image/*"
            onChange={(event) => void onSelectScreenshot(event.target.files?.[0] ?? null)}
          />
          <p className="subtle feedback-attachment-hint">
            {screenshotName ? `Attached: ${screenshotName}` : "Attach one screenshot up to 5 MB."}
          </p>
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
            {sending ? "Sending..." : "Send report"}
          </button>
        </div>
      </div>
    </div>
  );
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      const encoded = result.includes(",") ? result.split(",", 2)[1] : result;
      if (!encoded) {
        reject(new Error("empty file"));
        return;
      }
      resolve(encoded);
    };
    reader.onerror = () => reject(reader.error ?? new Error("file read failed"));
    reader.readAsDataURL(file);
  });
}
