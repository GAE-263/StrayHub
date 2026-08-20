"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

interface ToastProps {
  children: ReactNode;
  duration?: number;
  messageKey?: string | number;
  onClose?: () => void;
}

export function Toast({
  children,
  duration = 5000,
  messageKey,
  onClose,
}: ToastProps) {
  const [visible, setVisible] = useState(true);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  const dismiss = useCallback(() => {
    setVisible(false);
    onCloseRef.current?.();
  }, []);

  useEffect(() => {
    setVisible(true);
    if (duration <= 0) return;

    const timeoutId = window.setTimeout(dismiss, duration);
    return () => window.clearTimeout(timeoutId);
  }, [children, dismiss, duration, messageKey]);

  if (!visible) return null;

  return (
    <div
      className="ui-toast"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <span className="ui-toast-message">{children}</span>
      <button
        className="ui-toast-close"
        type="button"
        aria-label="關閉通知"
        onClick={dismiss}
      >
        ×
      </button>
    </div>
  );
}
