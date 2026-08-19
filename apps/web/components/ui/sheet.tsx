"use client";

import React, { useEffect, useId, useRef } from "react";
import type { ReactNode, SyntheticEvent } from "react";

export function Sheet({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const titleId = useId();
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
      className="ui-sheet"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onCancel={handleCancel}
    >
      <div className="ui-overlay-heading">
        <h2 id={titleId}>{title}</h2>
        <button
          className="ui-overlay-close"
          type="button"
          aria-label="關閉"
          onClick={onClose}
        >
          ×
        </button>
      </div>
      {children}
    </dialog>
  );
}
