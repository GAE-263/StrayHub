"use client";

import React, { useEffect, useRef, useState } from "react";
import { LiffFallback } from "../../../features/line-bot/LiffFallback";
import { Button } from "../../../components/ui/button";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../../components/management/StateViews";
import { authFetch } from "../../../lib/auth";
import { useVolunteerShelterContext } from "../../../components/auth/VolunteerShelterContext";

type Draft = {
  id: string;
  answers: Record<string, string>;
  current_step: string;
  note?: string;
};

export default function CareReportPage() {
  const shelterContext = useVolunteerShelterContext();
  const contextRequestEpoch = useRef(0);
  const loadedContext = useRef<{
    initialized: boolean;
    organizationId: string | null;
  }>({ initialized: false, organizationId: null });
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);

  async function load(
    isCancelled: () => boolean = () => false,
    epoch = contextRequestEpoch.current,
  ) {
    if (isCancelled()) return;
    setLoading(true);
    setOffline(false);
    try {
      const response = await authFetch("/v1/line/care-report/drafts/current");
      if (response.status === 401 && !isCancelled()) setDraft(null);
      if (!response.ok && response.status !== 404) {
        throw new Error("目前無法連線");
      }
      const value: Draft | null =
        response.status === 204 || response.status === 404
          ? null
          : await response.json();
      if (!isCancelled() && contextRequestEpoch.current === epoch) {
        setDraft(value);
      }
    } catch {
      if (!isCancelled() && contextRequestEpoch.current === epoch) {
        setOffline(true);
      }
    } finally {
      if (!isCancelled() && contextRequestEpoch.current === epoch) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    const organizationId = shelterContext?.organizationId;
    if (!organizationId) return;
    if (
      loadedContext.current.initialized &&
      loadedContext.current.organizationId === organizationId
    ) {
      return;
    }
    loadedContext.current = { initialized: true, organizationId };
    const epoch = ++contextRequestEpoch.current;
    setDraft(null);
    void load(() => contextRequestEpoch.current !== epoch, epoch);
    // Initial draft restoration runs once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shelterContext?.organizationId]);

  const saveDraft = async (answers: Record<string, string>, note: string) => {
    if (!draft) return;
    const epoch = contextRequestEpoch.current;
    const draftId = draft.id;
    const response = await authFetch(`/v1/care-report-drafts/${draft.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers, note }),
    });
    if (contextRequestEpoch.current !== epoch) return;
    if (!response.ok) {
      if (response.status === 401) setDraft(null);
      throw new Error("草稿保存失敗，已保留原始輸入，請重試。");
    }
    const updatedDraft: Draft = await response.json();
    if (contextRequestEpoch.current === epoch && updatedDraft.id === draftId) {
      setDraft(updatedDraft);
    }
  };

  return (
    <main className="volunteer-page" aria-labelledby="care-report-title">
      <h1 id="care-report-title">照護回報備援介面</h1>
      {shelterContext?.organizationName && (
        <p role="status">目前協助收容所：{shelterContext.organizationName}</p>
      )}
      {loading && (
        <LoadingState
          title="正在恢復回報草稿…"
          description="正在取得上次保留的照護內容。"
        />
      )}
      {offline && (
        <ErrorState
          title="目前無法連線"
          description="已保留本頁內容，請稍後重試。"
          action={
            <Button
              variant="secondary"
              type="button"
              onClick={() => {
                const epoch = contextRequestEpoch.current;
                void load(() => contextRequestEpoch.current !== epoch, epoch);
              }}
            >
              重新連線
            </Button>
          }
        />
      )}
      {!loading && !offline && !draft && (
        <EmptyState
          title="目前沒有可恢復的照護回報"
          description="請從 LINE 照護流程開始新的回報。"
        />
      )}
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
