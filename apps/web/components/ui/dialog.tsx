"use client";

import React, { useEffect, useRef } from "react";
import type { ReactNode, SyntheticEvent } from "react";
import { cn } from "../../lib/utils";

export function Dialog({
  open,
  title,
  children,
  onClose,
  closeLabel = "關閉",
  role = "dialog",
  className,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
  closeLabel?: string;
  role?: "dialog" | "alertdialog";
  className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      previousFocus.current =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null;
      dialog.showModal();
    }
    if (!open && dialog.open) {
      dialog.close();
      window.requestAnimationFrame(() => previousFocus.current?.focus());
    }
  }, [open]);
  const handleCancel = (event: SyntheticEvent<HTMLDialogElement>) => {
    event.preventDefault();
    onClose();
  };
  return (
    <dialog
      ref={ref}
      className={cn("ui-dialog", className)}
      role={role}
      aria-modal="true"
      aria-labelledby="ui-dialog-title"
      onCancel={handleCancel}
    >
      <div className="ui-overlay-heading">
        <h2 id="ui-dialog-title">{title}</h2>
        <button
          className="ui-overlay-close"
          type="button"
          aria-label={closeLabel}
          onClick={onClose}
        >
          ×
        </button>
      </div>
      {children}
    </dialog>
  );
}
