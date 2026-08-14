"use client";

import React, { useRef, useState } from "react";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { Field } from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";

export type LiffFallbackProps = {
  initialAnswers?: Record<string, string>;
  draftId?: string;
  note?: string;
  onSave?: (
    answers: Record<string, string>,
    note: string,
  ) => void | Promise<void>;
  onRetryMedia?: () => void;
  onReselectAnimal?: () => void;
  onReturnToBot?: () => void;
};

const answerLabels: Record<string, string> = {
  care_completion: "照護完成",
  walk_completion: "散步完成",
  feeding: "進食",
  water: "飲水",
  activity: "活動",
  urination: "排尿",
  defecation: "排便",
  resource_guarding: "資源防衛",
  human_interaction: "與人互動",
  animal_interaction: "與動物互動",
  emotion: "情緒",
  walk_reaction: "散步反應",
  appearance_special_status: "外觀／特殊狀況",
};

export function LiffFallback({
  initialAnswers = {},
  draftId,
  note: initialNote = "",
  onSave,
  onRetryMedia,
  onReselectAnimal,
  onReturnToBot,
}: LiffFallbackProps = {}) {
  const [answers, setAnswers] = useState(initialAnswers);
  const [note, setNote] = useState(initialNote);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const savingRef = useRef(false);

  const save = async () => {
    if (savingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    setSaved(false);
    setError("");
    try {
      await onSave?.(answers, note);
      setSaved(true);
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "草稿保存失敗，請重試。",
      );
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  return (
    <Card
      className="volunteer-report-card"
      aria-labelledby="liff-fallback-title"
    >
      <h2 id="liff-fallback-title">補充回報</h2>
      <p>LINE Bot 中斷時，可恢復草稿、批次修改答案或輸入較長心得。</p>
      {draftId && <p aria-label="草稿識別">目前草稿：{draftId}</p>}
      <div className="form-grid" aria-label="回報答案">
        {Object.entries(answerLabels).map(([key, label]) => (
          <Field key={key}>
            <label htmlFor={`answer-${key}`}>{label}</label>
            <Input
              id={`answer-${key}`}
              name={key}
              value={answers[key] ?? ""}
              onChange={(event) => {
                setSaved(false);
                setAnswers((current) => ({
                  ...current,
                  [key]: event.target.value,
                }));
              }}
            />
          </Field>
        ))}
      </div>
      <Field>
        <label htmlFor="care-note">補充心得（選填）</label>
        <Textarea
          id="care-note"
          value={note}
          maxLength={5000}
          onChange={(event) => setNote(event.target.value)}
        />
      </Field>
      <p aria-live="polite">{note.length} 字</p>
      <div className="toolbar">
        <Button
          type="button"
          onClick={() => void save()}
          disabled={saving}
          aria-describedby="save-status"
        >
          {saving ? "儲存中…" : "儲存並繼續"}
        </Button>
        <Button variant="secondary" type="button" onClick={onRetryMedia}>
          重新附加照片
        </Button>
        <Button variant="secondary" type="button" onClick={onReselectAnimal}>
          重新選擇動物
        </Button>
        <Button variant="ghost" type="button" onClick={onReturnToBot}>
          回到 LINE Bot
        </Button>
      </div>
      <p id="save-status" role="status" aria-live="polite">
        {saving
          ? "正在保存原始回報，請不要重複提交。"
          : error || (saved ? "草稿已保存，可回到 LINE Bot 繼續。" : "")}
      </p>
    </Card>
  );
}
