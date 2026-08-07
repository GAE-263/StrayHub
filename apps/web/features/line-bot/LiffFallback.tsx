"use client";

import { useState } from "react";

export type LiffFallbackProps = {
  initialAnswers?: Record<string, string>;
  draftId?: string;
  note?: string;
  onSave?: (answers: Record<string, string>, note: string) => void;
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

  const save = () => {
    onSave?.(answers, note);
    setSaved(true);
  };

  return (
    <section aria-labelledby="liff-fallback-title">
      <h2 id="liff-fallback-title">補充回報</h2>
      <p>LINE Bot 中斷時，可恢復草稿、批次修改答案或輸入較長心得。</p>
      {draftId && <p aria-label="草稿識別">目前草稿：{draftId}</p>}
      <div aria-label="回報答案">
        {Object.entries(answerLabels).map(([key, label]) => (
          <label key={key}>
            {label}
            <input
              name={key}
              value={answers[key] ?? ""}
              onChange={(event) => {
                setSaved(false);
                setAnswers((current) => ({ ...current, [key]: event.target.value }));
              }}
            />
          </label>
        ))}
      </div>
      <label>
        補充心得（選填）
        <textarea value={note} maxLength={5000} onChange={(event) => setNote(event.target.value)} />
      </label>
      <p aria-live="polite">{note.length} 字</p>
      <div>
        <button type="button" onClick={save}>儲存並繼續</button>
        <button type="button" onClick={onRetryMedia}>重新附加照片</button>
        <button type="button" onClick={onReselectAnimal}>重新選擇動物</button>
        <button type="button" onClick={onReturnToBot}>回到 LINE Bot</button>
      </div>
      {saved && <p role="status">草稿已保存，可回到 LINE Bot 繼續。</p>}
    </section>
  );
}
