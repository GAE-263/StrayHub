"use client";

import React, { useState } from "react";

export type AIObservationStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "invalid"
  | "confirmed"
  | "rejected"
  | "corrected";

export type AIObservationView = {
  id: string;
  status: AIObservationStatus;
  sourceType: "note" | "photo";
  sourceId: string | null;
  rawAiOutput: unknown;
  validatedAiObservation: Record<string, unknown> | null;
  humanReviewResult: Record<string, unknown> | null;
  failureReason?: string | null;
};

type ReviewAction = "confirm" | "reject" | "correct";

type Props = {
  observation: AIObservationView;
  onReview?: (
    action: ReviewAction,
    result?: Record<string, unknown>,
  ) => void | Promise<void>;
};

const statusLabels: Record<AIObservationStatus, string> = {
  pending: "等待 AI 處理",
  running: "AI 處理中",
  succeeded: "待人工確認",
  failed: "AI 處理失敗",
  invalid: "AI 輸出無效",
  confirmed: "人工已確認",
  rejected: "人工已拒絕",
  corrected: "人工已修正",
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "尚無資料";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2) ?? "尚無資料";
}

export function AIObservationPanel({ observation, onReview }: Props) {
  const [correction, setCorrection] = useState("");
  const canReview = observation.status === "succeeded";
  const sourceLabel = observation.sourceType === "photo" ? "清理後照片" : "志工心得";

  const review = (action: ReviewAction) => {
    if (!onReview) return;
    if (action === "correct") {
      onReview(action, {
        observations: [{ description: correction }],
      });
      return;
    }
    onReview(action);
  };

  return (
    <section aria-labelledby={`ai-observation-${observation.id}`}>
      <h2 id={`ai-observation-${observation.id}`}>AI 輔助擷取</h2>
      <p role="status">狀態：{statusLabels[observation.status]}</p>
      <p>
        來源：{sourceLabel}（{observation.sourceId ?? "未提供來源識別"}）
      </p>

      <section aria-labelledby={`ai-original-${observation.id}`}>
        <h3 id={`ai-original-${observation.id}`}>原始資料</h3>
        <pre>{formatValue(observation.rawAiOutput)}</pre>
      </section>

      <section aria-labelledby={`ai-result-${observation.id}`}>
        <h3 id={`ai-result-${observation.id}`}>AI 擷取結果</h3>
        {observation.status === "failed" || observation.status === "invalid" ? (
          <p role="alert">
            {statusLabels[observation.status]}
            {observation.failureReason ? `：${observation.failureReason}` : "。"}
          </p>
        ) : (
          <pre>{formatValue(observation.validatedAiObservation)}</pre>
        )}
      </section>

      <section aria-labelledby={`ai-review-${observation.id}`}>
        <h3 id={`ai-review-${observation.id}`}>人工覆核結果</h3>
        <pre>{formatValue(observation.humanReviewResult)}</pre>
        {canReview && (
          <div>
            <button type="button" onClick={() => review("confirm")}>
              確認
            </button>
            <button type="button" onClick={() => review("reject")}>
              拒絕
            </button>
            <label>
              修正內容
              <input
                value={correction}
                onChange={(event) => setCorrection(event.target.value)}
              />
            </label>
            <button type="button" onClick={() => review("correct")} disabled={!correction}>
              修正
            </button>
          </div>
        )}
      </section>
    </section>
  );
}
