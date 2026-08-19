"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { authFetch } from "../../../lib/auth";
import {
  EmptyState,
  LoadingState,
} from "../../../components/management/StateViews";
import { Alert } from "../../../components/ui/alert";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../../components/ui/card";
import { Field } from "../../../components/ui/field";
import { Select } from "../../../components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../../components/ui/table";

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

const statusLabels: Record<string, string> = {
  pending: "待處理",
  running: "AI 處理中",
  succeeded: "需要人工覆核",
  failed: "AI 處理失敗",
  invalid: "AI 輸出無效",
  confirmed: "人工已確認",
  rejected: "人工已拒絕",
  corrected: "人工已修正",
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
    <section aria-labelledby="ai-review-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">AI REVIEW QUEUE</span>
          <h1 id="ai-review-title">AI Review Queue</h1>
          <p>AI 只提供可追溯提示；人工決定另存，不改寫原始回報。</p>
        </div>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>AI 待覆核清單</CardTitle>
          <Field>
            <label htmlFor="ai-status">狀態</label>
            <Select
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
            </Select>
          </Field>
        </CardHeader>
        <CardContent>
          {loading ? (
            <LoadingState title="正在載入 AI Queue…" />
          ) : error ? (
            <Alert role="alert">
              <strong>無法載入 AI Queue</strong>
              <p>{error}</p>
            </Alert>
          ) : items.length === 0 ? (
            <EmptyState title="目前沒有符合條件的 AI Observation" />
          ) : (
            <Table>
              <TableHeader>
                <tr>
                  <TableHead>來源</TableHead>
                  <TableHead>狀態</TableHead>
                  <TableHead>失敗原因</TableHead>
                  <TableHead>原始資料</TableHead>
                  <TableHead>操作</TableHead>
                </tr>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
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
                    </TableCell>
                    <TableCell>
                      <Badge>{statusLabels[item.status] ?? item.status}</Badge>
                    </TableCell>
                    <TableCell>{item.failure_reason ?? "—"}</TableCell>
                    <TableCell>
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
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="secondary"
                        type="button"
                        disabled={
                          item.status === "confirmed" ||
                          item.status === "rejected"
                        }
                        onClick={() => void review(item, "confirm")}
                      >
                        確認
                      </Button>{" "}
                      <Button
                        variant="secondary"
                        type="button"
                        disabled={
                          item.status === "confirmed" ||
                          item.status === "rejected"
                        }
                        onClick={() => void review(item, "reject")}
                      >
                        拒絕
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
