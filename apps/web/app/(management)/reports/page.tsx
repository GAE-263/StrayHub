"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { authFetch } from "../../../lib/auth";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PermissionDeniedState,
} from "../../../components/management/StateViews";
import { statusLabel } from "../../../components/management/ui-status";
import { Badge } from "../../../components/ui/badge";
import { Field } from "../../../components/ui/field";
import { Input } from "../../../components/ui/input";
import { Select } from "../../../components/ui/select";
import { Table } from "../../../components/ui/table";
import { buildReportsQuery } from "../management-query";

type Report = {
  id: string;
  animal_id: string;
  animal_name: string | null;
  status: string;
  ai_job_status: string;
  submitted_at: string;
  note: string | null;
};
type ResponseData = {
  items: Report[];
  page: number;
  page_size: number;
  total: number;
};

export default function ReportsPage() {
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [status, setStatus] = useState("");
  const [data, setData] = useState<ResponseData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [permissionDenied, setPermissionDenied] = useState(false);
  const latestRequest = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const requestId = ++latestRequest.current;
    const params = buildReportsQuery({ fromDate, toDate, status });
    setLoading(true);
    setError("");
    setPermissionDenied(false);
    void authFetch(`/v1/management/reports?${params}`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.status === 403) {
          if (requestId !== latestRequest.current) return;
          setData(null);
          setPermissionDenied(true);
          return;
        }
        if (!response.ok)
          throw new Error(`Report Inbox 載入失敗（HTTP ${response.status}）`);
        const nextData = (await response.json()) as ResponseData;
        if (!controller.signal.aborted && requestId === latestRequest.current)
          setData(nextData);
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted && requestId === latestRequest.current)
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Report Inbox 載入失敗",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted && requestId === latestRequest.current)
          setLoading(false);
      });
    return () => controller.abort();
  }, [fromDate, status, toDate]);

  return (
    <main aria-labelledby="reports-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">REPORT INBOX</span>
          <h1 id="reports-title">回報收件匣</h1>
          <p>保留志工原始回報，集中處理狀態、AI 提示與可追溯修正。</p>
        </div>
      </div>
      <section className="panel ui-card">
        <div className="toolbar">
          <Field>
            <label htmlFor="report-from">開始日期</label>
            <Input
              id="report-from"
              type="date"
              value={fromDate}
              onChange={(event) => setFromDate(event.target.value)}
            />
          </Field>
          <Field>
            <label htmlFor="report-to">結束日期</label>
            <Input
              id="report-to"
              type="date"
              value={toDate}
              onChange={(event) => setToDate(event.target.value)}
            />
          </Field>
          <Field>
            <label htmlFor="report-status">狀態</label>
            <Select
              id="report-status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">全部</option>
              <option value="saved">已保存</option>
              <option value="amended">已修正</option>
              <option value="archived">已封存</option>
            </Select>
          </Field>
        </div>
        {loading ? <LoadingState title="正在載入回報…" /> : null}
        {permissionDenied ? (
          <PermissionDeniedState description="請切換到已授權收容所，或聯絡收容所管理者。" />
        ) : null}
        {error ? (
          <ErrorState title="無法載入 Report Inbox" description={error} />
        ) : null}
        {!loading && !error && data?.items.length === 0 ? (
          <EmptyState
            title="目前沒有符合條件的回報"
            description="調整日期或狀態篩選後再試。"
          />
        ) : null}
        {!loading && !error && data?.items.length ? (
          <Table>
            <thead>
              <tr>
                <th>提交時間</th>
                <th>動物</th>
                <th>狀態</th>
                <th>AI</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((report) => (
                <tr key={report.id}>
                  <td>
                    {new Date(report.submitted_at).toLocaleString("zh-TW")}
                  </td>
                  <td>
                    <Link
                      className="text-link"
                      href={`/animals/${report.animal_id}`}
                    >
                      {report.animal_name ?? report.animal_id.slice(0, 8)}
                    </Link>
                  </td>
                  <td>
                    <Badge>{statusLabel(report.status)}</Badge>
                  </td>
                  <td>{statusLabel(report.ai_job_status)}</td>
                  <td>
                    <Link className="text-link" href={`/reports/${report.id}`}>
                      查看 Detail →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : null}
      </section>
    </main>
  );
}
