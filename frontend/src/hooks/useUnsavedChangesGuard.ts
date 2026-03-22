import { useCallback, useEffect, useState } from "react";

interface UnsavedChangesGuardOptions {
  isDirty: boolean;
  onSave: () => Promise<void> | void;
  onDiscard: () => void;
}

interface UnsavedChangesGuardState {
  showPrompt: boolean;
  onSaveAndContinue: () => Promise<void>;
  onDiscardAndContinue: () => void;
}

export function useUnsavedChangesGuard({
  isDirty,
  onSave,
  onDiscard,
}: UnsavedChangesGuardOptions): UnsavedChangesGuardState {
  const [pendingPath, setPendingPath] = useState<string | null>(null);

  const continueNavigation = useCallback((path: string | null): void => {
    if (!path) {
      return;
    }
    if (path === `${window.location.pathname}${window.location.search}${window.location.hash}`) {
      return;
    }
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, []);

  useEffect(() => {
    if (!isDirty) {
      return undefined;
    }
    const onBeforeUnload = (event: BeforeUnloadEvent): void => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
    };
  }, [isDirty]);

  useEffect(() => {
    if (!isDirty) {
      setPendingPath(null);
      return undefined;
    }
    const onDocumentClick = (event: MouseEvent): void => {
      if (event.defaultPrevented) {
        return;
      }
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }
      const target = event.target as HTMLElement | null;
      const anchor = target?.closest("a[href]");
      if (!(anchor instanceof HTMLAnchorElement)) {
        return;
      }
      if (anchor.target && anchor.target !== "_self") {
        return;
      }
      const rawHref = anchor.getAttribute("href");
      if (!rawHref || rawHref.startsWith("#")) {
        return;
      }
      const href = new URL(rawHref, window.location.origin);
      if (href.origin !== window.location.origin) {
        return;
      }
      const nextPath = `${href.pathname}${href.search}${href.hash}`;
      const currentPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
      if (nextPath === currentPath) {
        return;
      }
      event.preventDefault();
      setPendingPath(nextPath);
    };

    document.addEventListener("click", onDocumentClick, true);
    return () => {
      document.removeEventListener("click", onDocumentClick, true);
    };
  }, [isDirty]);

  const onSaveAndContinue = useCallback(async (): Promise<void> => {
    const targetPath = pendingPath;
    await onSave();
    setPendingPath(null);
    continueNavigation(targetPath);
  }, [pendingPath, onSave, continueNavigation]);

  const onDiscardAndContinue = useCallback((): void => {
    onDiscard();
    const targetPath = pendingPath;
    setPendingPath(null);
    continueNavigation(targetPath);
  }, [onDiscard, pendingPath, continueNavigation]);

  return {
    showPrompt: Boolean(pendingPath),
    onSaveAndContinue,
    onDiscardAndContinue,
  };
}
