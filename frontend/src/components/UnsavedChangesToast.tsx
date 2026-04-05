interface UnsavedChangesToastProps {
  open: boolean;
  message?: string;
  busy?: boolean;
  onSave?: () => void;
  onDiscard?: () => void;
  className?: string;
}

export function UnsavedChangesToast({
  open,
  message = "There are unsaved changes",
  busy = false,
  onSave,
  onDiscard,
  className = "",
}: UnsavedChangesToastProps): JSX.Element | null {
  if (!open) {
    return null;
  }

  return (
    <div className={`unsaved-changes-toast ${className}`.trim()} role="status" aria-live="polite">
      <span>{message}</span>
      {onSave && onDiscard ? (
        <div className="unsaved-changes-actions">
          <button type="button" className="modal-button modal-primary" onClick={onSave} disabled={busy}>
            {busy ? "Saving..." : "Save"}
          </button>
          <button type="button" className="modal-button" onClick={onDiscard} disabled={busy}>
            Discard
          </button>
        </div>
      ) : null}
    </div>
  );
}
