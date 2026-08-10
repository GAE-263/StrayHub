"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { authFetch } from "../../../lib/auth";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../../components/management/StateViews";

type Observation = {
  id: string;
  source_type: string;
  source_id: string | null;
  status: string;
  failure_reason: string | null;
  raw_ai_output: unknown;
  validated_ai_observation: unknown;
  human_review_result: unknown;
};

export default function AiReviewPage() {
  const [status, setStatus] = useState("");
  const [items, setItems] = useState<Observation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = () => {
    setLoading(true);
    const params = new URLSearchParams({ limit: "100" });
    if (status) params.set("status", status);
    void authFetch(`/v1/management/ai-review?${params}`)
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`AI Queue 載入失敗（HTTP ${response.status}）`);
        setItems(((await response.json()) as { items: Observation[] }).items);
      })
      .catch((requestError: unknown) =>
        setError(
          requestError instanceof Error
            ? requestError.message
            : "AI Queue 載入失敗",
        ),
      )
      .finally(() => setLoading(false));
  };
  useEffect(load, [status]);
  const review = async (
    observation: Observation,
    action: "confirm" | "reject",
  ) => {
    const reason = window.prompt(
      action === "confirm" ? "確認原因" : "拒絕原因",
    );
    if (!reason) return;
    const response = await authFetch(
      `/v1/management/ai-review/${observation.id}/review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, reason }),
      },
    );
    if (!response.ok) setError(`AI 覆核失敗（HTTP ${response.status}）`);
    else load();
  };
  return (
    <main aria-labelledby="ai-review-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">AI REVIEW QUEUE</span>
          <h1 id="ai-review-title">AI Review Queue</h1>
          <p>AI 只提供可追溯提示；人工決定另存，不改寫原始回報。</p>
        </div>
      </div>
      <section className="panel">
        <div className="toolbar">
          <div className="field">
            <label htmlFor="ai-status">狀態</label>
            <select
              id="ai-status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">全部</option>
              <option value="pending">待處理</option>
              <option value="succeeded">成功</option>
              <option value="failed">失敗</option>
              <option value="invalid">無效</option>
              <option value="confirmed">已確認</option>
              <option value="rejected">已拒絕</option>
              <option value="corrected">已修正</option>
            </select>
          </div>
        </div>
        {loading ? (
          <LoadingState title="正在載入 AI Queue…" />
        ) : error ? (
          <ErrorState title="無法載入 AI Queue" description={error} />
        ) : items.length === 0 ? (
          <EmptyState title="目前沒有符合條件的 AI Observation" />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>來源</th>
                  <th>狀態</th>
                  <th>失敗原因</th>
                  <th>原始資料</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      {item.source_type}{" "}
                      {item.source_id ? (
                        <Link
                          className="text-link"
                          href={`/reports/${item.source_id}`}
                        >
                          查看來源
                        </Link>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      <span className="badge">{item.status}</span>
                    </td>
                    <td>{item.failure_reason ?? "—"}</td>
                    <td>
                      <details>
                        <summary>查看</summary>
                        <pre className="json-view">
                          {JSON.stringify(
                            {
                              raw: item.raw_ai_output,
                              validated: item.validated_ai_observation,
                            },
                            null,
                            2,
                          )}
                        </pre>
                      </details>
                    </td>
                    <td>
                      <button
                        className="button button-secondary"
                        type="button"
                        disabled={
                          item.status === "confirmed" ||
                          item.status === "rejected"
                        }
                        onClick={() => void review(item, "confirm")}
                      >
                        確認
                      </button>{" "}
                      <button
                        className="button button-secondary"
                        type="button"
                        disabled={
                          item.status === "confirmed" ||
                          item.status === "rejected"
                        }
                        onClick={() => void review(item, "reject")}
                      >
                        拒絕
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
