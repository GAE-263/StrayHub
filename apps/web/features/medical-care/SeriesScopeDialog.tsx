"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button } from "../../components/ui/button";
import { Dialog } from "../../components/ui/dialog";
import { Field } from "../../components/ui/field";
import { Select } from "../../components/ui/select";
import { Textarea } from "../../components/ui/textarea";

export function SeriesScopeDialog({
  open,
  onClose,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (
    scope: "this" | "this_and_future",
    reason: string,
  ) => Promise<void>;
}) {
  const [scope, setScope] = useState<"this" | "this_and_future">("this");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) {
      setScope("this");
      setReason("");
      setError("");
    }
  }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !reason.trim()) return;
    setBusy(true);
    setError("");
    try {
      await onSubmit(scope, reason.trim());
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "提醒修改失敗");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} title="選擇提醒修改範圍" onClose={onClose}>
      <form className="stack-sm" onSubmit={submit}>
        <Field>
          <label htmlFor="series-scope">修改範圍</label>
          <Select
            id="series-scope"
            value={scope}
            onChange={(event) =>
              setScope(event.target.value as "this" | "this_and_future")
            }
          >
            <option value="this">只修改這一次</option>
            <option value="this_and_future">修改這一次及未來提醒</option>
          </Select>
        </Field>
        <p className="muted">
          過去已完成的提醒不會被修改；選擇未來提醒會從本次開始套用新規則。
        </p>
        <Field>
          <label htmlFor="series-scope-reason">修改原因</label>
          <Textarea
            id="series-scope-reason"
            required
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </Field>
        <Button type="submit" disabled={busy || !reason.trim()}>
          {busy ? "儲存中…" : "確認修改"}
        </Button>
        {error ? <p role="alert">{error}</p> : null}
      </form>
    </Dialog>
  );
}
