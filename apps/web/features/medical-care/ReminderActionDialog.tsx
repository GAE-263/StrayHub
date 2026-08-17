"use client";

import React from "react";
import { FormEvent, useEffect, useState } from "react";
import { Button } from "../../components/ui/button";
import { Dialog } from "../../components/ui/dialog";
import { Field } from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { Textarea } from "../../components/ui/textarea";
import { actOnReminder } from "./api";
import type { AgendaItem } from "./types";

export function ReminderActionDialog({
  item,
  onClose,
  onSaved,
}: {
  item: AgendaItem | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [action, setAction] = useState<
    "completed" | "skipped" | "cancelled" | "rescheduled"
  >("completed");
  const [reason, setReason] = useState("");
  const [resultNote, setResultNote] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [actualCompletedAt, setActualCompletedAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!item) return;
    setAction("completed");
    setReason("");
    setResultNote("");
    setScheduledAt("");
    setActualCompletedAt("");
    setMessage("");
  }, [item]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!item || busy) return;
    setBusy(true);
    setMessage("");
    try {
      await actOnReminder(item.occurrence_id, {
        action,
        expected_version: item.version,
        reason: reason || undefined,
        result_note: resultNote || undefined,
        scheduled_at: scheduledAt
          ? new Date(scheduledAt).toISOString()
          : undefined,
        actual_completed_at: actualCompletedAt
          ? new Date(actualCompletedAt).toISOString()
          : undefined,
      });
      onSaved();
      onClose();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "提醒處理失敗");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={Boolean(item)}
      title={`處理提醒：${item?.title ?? ""}`}
      onClose={onClose}
    >
      <form className="stack-sm" onSubmit={submit}>
        <Field>
          <label htmlFor="reminder-action">處理方式</label>
          <Select
            id="reminder-action"
            value={action}
            onChange={(event) => setAction(event.target.value as typeof action)}
          >
            <option value="completed">標記完成</option>
            <option value="skipped">略過</option>
            <option value="rescheduled">改期</option>
            <option value="cancelled">取消本次</option>
          </Select>
        </Field>
        {action === "completed" ? (
          <>
            <Field>
              <label htmlFor="actual-completed-at">實際完成時間（選填）</label>
              <Input
                id="actual-completed-at"
                type="datetime-local"
                value={actualCompletedAt}
                onChange={(event) => setActualCompletedAt(event.target.value)}
              />
            </Field>
            <Field>
              <label htmlFor="reminder-result">結果或備註（選填）</label>
              <Textarea
                id="reminder-result"
                value={resultNote}
                onChange={(event) => setResultNote(event.target.value)}
              />
            </Field>
          </>
        ) : (
          <Field>
            <label htmlFor="reminder-reason">原因</label>
            <Textarea
              id="reminder-reason"
              required
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </Field>
        )}
        {action === "rescheduled" ? (
          <Field>
            <label htmlFor="reminder-reschedule-at">新的執行時間</label>
            <Input
              id="reminder-reschedule-at"
              required
              type="datetime-local"
              value={scheduledAt}
              onChange={(event) => setScheduledAt(event.target.value)}
            />
          </Field>
        ) : null}
        <div className="toolbar">
          <Button type="submit" disabled={busy}>
            {busy ? "處理中…" : "確認處理"}
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={busy}
            onClick={onClose}
          >
            返回
          </Button>
        </div>
        {message ? <p role="alert">{message}</p> : null}
      </form>
    </Dialog>
  );
}
