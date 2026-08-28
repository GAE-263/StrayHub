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
import { buildAdoptionInquiriesQuery } from "../management-query";

type AdoptionInquiry = {
  id: string;
  path: string;
  target_animal_id: string;
  animal_name: string | null;
  animal_name_snapshot: string;
  status: string;
  submitted_at: string;
};
type ResponseData = {
  items: AdoptionInquiry[];
  page: number;
  page_size: number;
  total: number;
};

const PATH_LABELS: Record<string, string> = {
  specific_animal: "已有目標動物",
  recommend_me: "系統推薦",
};

export default function AdoptionInquiriesPage() {
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
    const params = buildAdoptionInquiriesQuery({ fromDate, toDate, status });
    setLoading(true);
    setError("");
    setPermissionDenied(false);
    void authFetch(`/v1/management/adoption-inquiries?${params}`, {
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
          throw new Error(`領養意願收件匣載入失敗（HTTP ${response.status}）`);
        const nextData = (await response.json()) as ResponseData;
        if (!controller.signal.aborted && requestId === latestRequest.current)
          setData(nextData);
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted && requestId === latestRequest.current)
          setError(
            requestError instanceof Error
              ? requestError.message
              : "領養意願收件匣載入失敗",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted && requestId === latestRequest.current)
          setLoading(false);
      });
    return () => controller.abort();
  }, [fromDate, status, toDate]);

  return (
    <section aria-labelledby="adoption-inquiries-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">ADOPTION INQUIRY INBOX</span>
          <h1 id="adoption-inquiries-title">領養意願收件匣</h1>
          <p>透過 LINE 領養媒合送出的領養意願，集中在這裡追蹤與聯絡。</p>
        </div>
      </div>
      <section className="ui-card ui-card-padded">
        <div className="toolbar">
          <Field>
            <label htmlFor="adoption-from">開始日期</label>
            <Input
              id="adoption-from"
              type="date"
              value={fromDate}
              onChange={(event) => setFromDate(event.target.value)}
            />
          </Field>
          <Field>
            <label htmlFor="adoption-to">結束日期</label>
            <Input
              id="adoption-to"
              type="date"
              value={toDate}
              onChange={(event) => setToDate(event.target.value)}
            />
          </Field>
          <Field>
            <label htmlFor="adoption-status">狀態</label>
            <Select
              id="adoption-status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">全部</option>
              <option value="new">新申請</option>
              <option value="contacted">已聯絡</option>
              <option value="in_review">審核中</option>
              <option value="closed">已結案</option>
            </Select>
          </Field>
        </div>
        {loading ? <LoadingState title="正在載入領養意願…" /> : null}
        {permissionDenied ? (
          <PermissionDeniedState description="請切換到已授權收容所，或聯絡收容所管理者。" />
        ) : null}
        {error ? (
          <ErrorState title="無法載入領養意願收件匣" description={error} />
        ) : null}
        {!loading && !error && data?.items.length === 0 ? (
          <EmptyState
            title="目前沒有符合條件的領養意願"
            description="調整日期或狀態篩選後再試。"
          />
        ) : null}
        {!loading && !error && data?.items.length ? (
          <Table>
            <thead>
              <tr>
                <th>送出時間</th>
                <th>動物</th>
                <th>方式</th>
                <th>狀態</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((inquiry) => (
                <tr key={inquiry.id}>
                  <td>
                    {new Date(inquiry.submitted_at).toLocaleString("zh-TW")}
                  </td>
                  <td>
                    <Link
                      className="text-link"
                      href={`/animals/${inquiry.target_animal_id}`}
                    >
                      {inquiry.animal_name ?? inquiry.animal_name_snapshot}
                    </Link>
                  </td>
                  <td>{PATH_LABELS[inquiry.path] ?? inquiry.path}</td>
                  <td>
                    <Badge>{statusLabel(inquiry.status)}</Badge>
                  </td>
                  <td>
                    <Link
                      className="text-link"
                      href={`/adoption-inquiries/${inquiry.id}`}
                    >
                      查看詳情 →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : null}
      </section>
    </section>
  );
}
