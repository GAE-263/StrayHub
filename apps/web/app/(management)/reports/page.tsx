"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { authFetch } from "../../../lib/auth";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../../components/management/StateViews";

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

  useEffect(() => {
    const params = new URLSearchParams({ page: "1", page_size: "50" });
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    if (status) params.set("status", status);
    setLoading(true);
    void authFetch(`/v1/management/reports?${params}`)
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`Report Inbox 載入失敗（HTTP ${response.status}）`);
        setData((await response.json()) as ResponseData);
      })
      .catch((requestError: unknown) =>
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Report Inbox 載入失敗",
        ),
      )
      .finally(() => setLoading(false));
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
      <section className="panel">
        <div className="toolbar">
          <div className="field">
            <label htmlFor="report-from">開始日期</label>
            <input
              id="report-from"
              type="date"
              value={fromDate}
              onChange={(event) => setFromDate(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="report-to">結束日期</label>
            <input
              id="report-to"
              type="date"
              value={toDate}
              onChange={(event) => setToDate(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="report-status">狀態</label>
            <select
              id="report-status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">全部</option>
              <option value="saved">已保存</option>
              <option value="amended">已修正</option>
              <option value="archived">已封存</option>
            </select>
          </div>
        </div>
        {loading ? <LoadingState title="正在載入回報…" /> : null}
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
          <div className="table-wrap">
            <table>
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
                      <span className="badge">{report.status}</span>
                    </td>
                    <td>{report.ai_job_status}</td>
                    <td>
                      <Link
                        className="text-link"
                        href={`/reports/${report.id}`}
                      >
                        查看 Detail →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </main>
  );
}
