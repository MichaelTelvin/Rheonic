import { useEffect, useRef, useState } from "react";

import { UnsavedChangesToast } from "./UnsavedChangesToast";

const TOAST_EVENT_NAME = "rheonic:app-toast";

interface ToastEventDetail {
  message: string;
}

export function showAppToast(message: string): void {
  if (!message.trim()) {
    return;
  }
  window.dispatchEvent(
    new CustomEvent<ToastEventDetail>(TOAST_EVENT_NAME, {
      detail: { message: message.trim() },
    }),
  );
}

export function AppToastHost(): JSX.Element | null {
  const [message, setMessage] = useState<string>("");
  const [open, setOpen] = useState<boolean>(false);
  const timeoutRef = useRef<number | null>(null);

  useEffect(() => {
    const onToast = (event: Event): void => {
      const custom = event as CustomEvent<ToastEventDetail>;
      const nextMessage = custom.detail?.message?.trim();
      if (!nextMessage) {
        return;
      }
      setMessage(nextMessage);
      setOpen(true);
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
      }
      timeoutRef.current = window.setTimeout(() => {
        setOpen(false);
        timeoutRef.current = null;
      }, 2200);
    };

    window.addEventListener(TOAST_EVENT_NAME, onToast as EventListener);
    return () => {
      window.removeEventListener(TOAST_EVENT_NAME, onToast as EventListener);
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return <UnsavedChangesToast open={open} message={message} />;
}
