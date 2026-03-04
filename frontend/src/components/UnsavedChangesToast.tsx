interface UnsavedChangesToastProps {
  open: boolean;
  busy?: boolean;
  onSave: () => void;
  onDiscard: () => void;
}

export function UnsavedChangesToast({
  open,
  busy = false,
  onSave,
  onDiscard,
}: UnsavedChangesToastProps): JSX.Element | null {
  if (!open) {
    return null;
  }

  return (
    <div className="unsaved-changes-toast" role="status" aria-live="polite">
      <span>There are unsaved changes</span>
      <div className="unsaved-changes-actions">
        <button type="button" className="modal-button modal-primary" onClick={onSave} disabled={busy}>
          {busy ? "Saving..." : "Save"}
        </button>
        <button type="button" className="modal-button" onClick={onDiscard} disabled={busy}>
          Discard
        </button>
      </div>
    </div>
  );
}
