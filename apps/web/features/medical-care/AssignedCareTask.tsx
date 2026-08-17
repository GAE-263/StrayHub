"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button } from "../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { Field } from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { Textarea } from "../../components/ui/textarea";
import { actOnAssignedCare, fetchAssignedCare } from "./api";
import type { AssignedCareItem } from "./types";

const reminderTypeLabels: Record<string, string> = {
  medication: "吃藥",
  follow_up: "回診",
  weight: "量體重",
  vaccination: "疫苗",
  examination: "檢查",
  other: "其他",
};

const statusLabels: Record<string, string> = {
  pending: "待處理",
  completed: "已完成",
  skipped: "已略過",
  cancelled: "已取消",
};

function displayLocalTime(value: string) {
  return value.slice(0, 16).replace("T", " ");
}

export function AssignedCareTask({ occurrenceId }: { occurrenceId: string }) {
  const [item, setItem] = useState<AssignedCareItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [action, setAction] = useState<"complete" | "skip">("complete");
  const [actualCompletedAt, setActualCompletedAt] = useState("");
  const [resultNote, setResultNote] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function load(signal?: AbortSignal) {
    setLoading(true);
    setLoadError("");
    try {
      setItem(await fetchAssignedCare(occurrenceId, signal));
    } catch (error) {
      if (signal?.aborted) return;
      setLoadError(error instanceof Error ? error.message : "指派事項載入失敗");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [occurrenceId]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!item || busy) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await actOnAssignedCare(item.occurrence_id, {
        action,
        expected_version: item.version,
        actual_completed_at:
          action === "complete" && actualCompletedAt
            ? new Date(actualCompletedAt).toISOString()
            : null,
        result_note: action === "complete" ? resultNote || null : null,
        reason: action === "skip" ? reason : null,
      });
      setItem(result.occurrence);
      setMessage(action === "complete" ? "已回報完成。" : "已回報略過。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "指派事項處理失敗");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <p role="status">正在載入指派事項…</p>;
  }
  if (loadError) {
    return (
      <div className="notice error" role="alert">
        <p>{loadError}</p>
        <Button type="button" onClick={() => void load()}>
          重新載入
        </Button>
      </div>
    );
  }
  if (!item) {
    return <p role="status">目前沒有可查看的指派事項。</p>;
  }

  return (
    <div className="stack-md">
      <Card>
        <CardHeader>
          <CardTitle>{item.title}</CardTitle>
        </CardHeader>
        <CardContent className="stack-sm">
          <div className="cluster">
            {item.animal.photo_url ? (
              <img
                src={item.animal.photo_url}
                alt={`${item.animal.name}的照片`}
                width={96}
                height={96}
              />
            ) : (
              <div aria-label="目前沒有動物照片">無照片</div>
            )}
            <div>
              <p>
                <strong>{item.animal.name}</strong>
              </p>
              <p>收容編號：{item.animal.shelter_number ?? "未維護"}</p>
            </div>
          </div>
          <p>類型：{reminderTypeLabels[item.reminder_type] ?? "其他"}</p>
          <p>預定時間：{displayLocalTime(item.display_local_at)}</p>
          <p>狀態：{statusLabels[item.status] ?? item.status}</p>
          <div>
            <strong>執行指示</strong>
            <p>{item.instructions || "沒有補充指示"}</p>
          </div>
        </CardContent>
      </Card>

      {item.can_complete || item.can_skip ? (
        <form className="stack-sm" onSubmit={submit}>
          <Field>
            <label htmlFor="assigned-action">回報方式</label>
            <Select
              id="assigned-action"
              value={action}
              onChange={(event) =>
                setAction(event.target.value as "complete" | "skip")
              }
            >
              <option value="complete">完成</option>
              <option value="skip">略過</option>
            </Select>
          </Field>
          {action === "complete" ? (
            <>
              <Field>
                <label htmlFor="assigned-actual-completed-at">
                  實際完成時間（選填）
                </label>
                <Input
                  id="assigned-actual-completed-at"
                  type="datetime-local"
                  value={actualCompletedAt}
                  onChange={(event) => setActualCompletedAt(event.target.value)}
                />
              </Field>
              <Field>
                <label htmlFor="assigned-result-note">結果或備註（選填）</label>
                <Textarea
                  id="assigned-result-note"
                  value={resultNote}
                  onChange={(event) => setResultNote(event.target.value)}
                />
              </Field>
            </>
          ) : (
            <Field>
              <label htmlFor="assigned-skip-reason">略過原因</label>
              <Textarea
                id="assigned-skip-reason"
                required
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </Field>
          )}
          <Button type="submit" disabled={busy}>
            {busy ? "送出中…" : "確認回報"}
          </Button>
        </form>
      ) : (
        <p role="status">這筆事項已處理，無需再次回報。</p>
      )}

      {message ? (
        <p
          className={
            message.startsWith("已回報") ? "notice success" : "notice error"
          }
          role={message.startsWith("已回報") ? "status" : "alert"}
          aria-live="polite"
        >
          {message}
        </p>
      ) : null}
    </div>
  );
}
