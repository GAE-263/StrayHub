"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { authFetch } from "../../../lib/auth";
import {
  EmptyState,
  LoadingState,
} from "../../../components/management/StateViews";
import { Alert } from "../../../components/ui/alert";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Dialog } from "../../../components/ui/dialog";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../../components/ui/card";
import { Field } from "../../../components/ui/field";
import { Select } from "../../../components/ui/select";
import { Textarea } from "../../../components/ui/textarea";
import { Toast } from "../../../components/ui/toast";
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

type PendingReview = {
  observation: Observation;
  action: "confirm" | "reject";
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
  const [message, setMessage] = useState("");
  const [pendingReview, setPendingReview] = useState<PendingReview | null>(
    null,
  );
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const load = () => {
    setLoading(true);
    const params = new URLSearchParams({ limit: "100" });
    if (status) params.set("status", status);
    void authFetch(`/v1/management/ai-review?${params}`)
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`AI 人工覆核載入失敗（HTTP ${response.status}）`);
        setItems(((await response.json()) as { items: Observation[] }).items);
      })
      .catch((requestError: unknown) =>
        setError(
          requestError instanceof Error
            ? requestError.message
            : "AI 人工覆核載入失敗",
        ),
      )
      .finally(() => setLoading(false));
  };
  useEffect(load, [status]);
  const review = async (
    observation: Observation,
    action: "confirm" | "reject",
  ) => {
    setReason("");
    setPendingReview({ observation, action });
  };

  const confirmReview = async () => {
    if (!pendingReview || !reason.trim()) {
      setError("請填寫覆核原因。");
      return;
    }
    setError("");
    setSubmitting(true);
    try {
      const response = await authFetch(
        `/v1/management/ai-review/${pendingReview.observation.id}/review`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: pendingReview.action,
            reason: reason.trim(),
          }),
        },
      );
      if (!response.ok)
        throw new Error(`AI 覆核失敗（HTTP ${response.status}）`);
      setMessage(
        pendingReview.action === "confirm"
          ? "AI Observation 已確認。"
          : "AI Observation 已拒絕，原始輸出仍保留。",
      );
      setPendingReview(null);
      setReason("");
      load();
    } catch (requestError: unknown) {
      setError(
        requestError instanceof Error ? requestError.message : "AI 覆核失敗",
      );
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <section aria-labelledby="ai-review-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">AI REVIEW QUEUE</span>
          <h1 id="ai-review-title">AI 人工覆核</h1>
          <p>AI 只提供可追溯提示；人工決定另存，不改寫原始回報。</p>
        </div>
      </div>
      {message ? <Toast>{message}</Toast> : null}
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
            <LoadingState title="正在載入 AI 人工覆核…" />
          ) : error ? (
            <Alert role="alert">
              <strong>無法載入 AI 人工覆核</strong>
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
      <Dialog
        open={pendingReview !== null}
        role="alertdialog"
        title={
          pendingReview?.action === "reject"
            ? "拒絕 AI Observation"
            : "確認 AI Observation"
        }
        onClose={() => {
          if (!submitting) setPendingReview(null);
        }}
      >
        <p className="dialog-description">
          {pendingReview?.action === "reject"
            ? "拒絕會保留原始 AI 輸出，請記錄可追溯的拒絕原因。"
            : "確認會將人工覆核結果寫入 Audit，請記錄確認原因。"}
        </p>
        <Field>
          <label htmlFor="ai-review-reason">覆核原因</label>
          <Textarea
            id="ai-review-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="請輸入原因"
            required
            disabled={submitting}
          />
        </Field>
        <div className="dialog-actions">
          <Button
            type="button"
            variant="ghost"
            disabled={submitting}
            onClick={() => setPendingReview(null)}
          >
            取消
          </Button>
          <Button
            type="button"
            variant={
              pendingReview?.action === "reject" ? "destructive" : "default"
            }
            disabled={submitting || !reason.trim()}
            onClick={() => void confirmReview()}
          >
            {submitting
              ? "處理中…"
              : pendingReview?.action === "reject"
                ? "確認拒絕"
                : "確認覆核"}
          </Button>
        </div>
      </Dialog>
    </section>
  );
}
