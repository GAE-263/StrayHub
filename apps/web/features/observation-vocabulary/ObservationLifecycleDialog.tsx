import React, { useEffect, useState } from "react";
import { Alert } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Dialog } from "../../components/ui/dialog";
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
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
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
    <Dialog
      open
      title={`確認${labels[action]}`}
      onClose={onCancel}
      role="alertdialog"
    >
      <p>
        你要將「{option.display_name}」從「{optionStatusLabel(option.status)}
        」變更為「
        {labels[action]}」嗎？
      </p>
      <Alert>{irreversibleMessage}</Alert>
      {error ? <Alert role="alert">{error}</Alert> : null}
      <div className="p1-actions">
        <Button
          variant="secondary"
          type="button"
          onClick={onCancel}
          disabled={saving}
        >
          取消
        </Button>
        <Button
          variant={action === "disable" ? "destructive" : "default"}
          type="button"
          onClick={() => void confirm()}
          disabled={saving}
        >
          {saving ? "處理中…" : `確認${labels[action]}`}
        </Button>
      </div>
    </Dialog>
  );
}

export type { Action };
