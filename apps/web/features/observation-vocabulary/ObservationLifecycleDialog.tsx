import React, { useEffect, useRef, useState } from "react";
import { ObservationOption, optionStatusLabel } from "./observationVocabulary";

type Action = "disable" | "restore" | "archive";
type Props = {
  option: ObservationOption;
  action: Action;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
};

const labels: Record<Action, string> = {
  disable: "停用",
  restore: "恢復",
  archive: "封存",
};

export function ObservationLifecycleDialog({
  option,
  action,
  onConfirm,
  onCancel,
}: Props) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    cancelRef.current?.focus();
  }, []);
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) onCancel();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onCancel, saving]);
  const confirm = async () => {
    setSaving(true);
    setError("");
    try {
      await onConfirm();
    } catch (confirmError) {
      setError(
        confirmError instanceof Error
          ? confirmError.message
          : "操作失敗，請稍後再試。",
      );
    } finally {
      setSaving(false);
    }
  };
  const irreversibleMessage =
    action === "disable" || action === "archive"
      ? "不會出現在新的回報表單，但歷史回報仍會保留。"
      : "恢復後會重新出現在新的回報表單，歷史回報不會改變。";
  return (
    <div className="dialog-backdrop" role="presentation">
      <dialog
        className="observation-dialog"
        open
        aria-modal="true"
        aria-labelledby="lifecycle-dialog-title"
      >
        <h2 id="lifecycle-dialog-title">確認{labels[action]}</h2>
        <p>
          你要將「{option.display_name}」從「{optionStatusLabel(option.status)}
          」變更為「
          {labels[action]}」嗎？
        </p>
        <p className="notice warning">{irreversibleMessage}</p>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="dialog-actions">
          <button
            ref={cancelRef}
            className="button button-secondary"
            type="button"
            onClick={onCancel}
            disabled={saving}
          >
            取消
          </button>
          <button
            className={`button ${action === "disable" ? "button-danger" : ""}`}
            type="button"
            onClick={() => void confirm()}
            disabled={saving}
          >
            {saving ? "處理中…" : `確認${labels[action]}`}
          </button>
        </div>
      </dialog>
    </div>
  );
}

export type { Action };
