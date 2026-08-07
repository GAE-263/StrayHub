"use client";

import { useEffect, useState } from "react";
import { LiffFallback } from "../../../features/line-bot/LiffFallback";

type Draft = {
  id: string;
  answers: Record<string, string>;
  current_step: string;
  note?: string;
};

export default function CareReportPage() {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/v1/line/care-report/drafts/current")
      .then((response) => (response.ok ? response.json() : null))
      .then((value: Draft | null) => {
        if (!cancelled) setDraft(value);
      })
      .catch(() => {
        if (!cancelled) setOffline(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const saveDraft = async (answers: Record<string, string>, note: string) => {
    if (!draft) return;
    const response = await fetch(`/v1/care-report-drafts/${draft.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers, note }),
    });
    if (response.ok) setDraft(await response.json());
  };

  return (
    <main>
      <h1>照護回報備援介面</h1>
      {loading && <p>正在恢復回報草稿…</p>}
      {offline && <p role="alert">目前無法連線；已保留本頁內容，請稍後重試。</p>}
      {!loading && !draft && <p>目前沒有可恢復的照護回報。</p>}
      {draft && (
        <>
          <p>目前步驟：{draft.current_step}</p>
          <LiffFallback
            draftId={draft.id}
            initialAnswers={draft.answers}
            note={draft.note}
            onSave={saveDraft}
          />
        </>
      )}
    </main>
  );
}
