"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { authFetch } from "../../../lib/auth";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PermissionDeniedState,
} from "../../../components/management/StateViews";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Dialog } from "../../../components/ui/dialog";
import { Field } from "../../../components/ui/field";
import { Input } from "../../../components/ui/input";
import { Select } from "../../../components/ui/select";
import { Table } from "../../../components/ui/table";
import { buildAdoptionInquiryQuery } from "../management-query";

type InquiryPath = "specific_animal" | "recommend_me";
type InquiryStatus = "new" | "contacted";

type AdoptionInquiry = {
  id: string;
  target_animal_id: string;
  animal_name: string;
  shelter_number: string | null;
  path: InquiryPath;
  adopter_name: string;
  phone_number: string;
  answers: Record<string, string>;
  answers_display: Array<{ key: string; label: string; value: string }>;
  status: InquiryStatus;
  staff_notes: string | null;
  submitted_at: string;
  status_updated_at: string | null;
  ai_suitability_score: number | null;
  ai_suitability_explanation: string | null;
  ai_recommendation_overridden: boolean | null;
};

type ResponseData = {
  items: AdoptionInquiry[];
  page: number;
  page_size: number;
  total: number;
};

const PATH_LABEL: Record<InquiryPath, string> = {
  specific_animal: "心有所屬",
  recommend_me: "推薦名單",
};

const NOWRAP_STYLE: CSSProperties = { whiteSpace: "nowrap" };
const STATUS_ACTION_STYLE: CSSProperties = {
  background: "var(--accent-soft)",
  border: "none",
  borderRadius: 999,
  color: "var(--primary)",
  cursor: "pointer",
  display: "inline-flex",
  font: "inherit",
  fontSize: 12,
  fontWeight: 700,
  padding: "4px 9px",
  whiteSpace: "nowrap",
};

function formatTimestamp(iso: string): { date: string; time: string } {
  const value = new Date(iso);
  return { date: value.toLocaleDateString("zh-TW"), time: value.toLocaleTimeString("zh-TW") };
}

function formatAnswers(display: Array<{ label: string; value: string }>): string {
  return display.map(({ label, value }) => `• ${label}：${value}`).join("\n");
}

export default function AdoptionInquiriesPage() {
  const [search, setSearch] = useState("");
  const [path, setPath] = useState("");
  const [status, setStatus] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ResponseData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [viewingText, setViewingText] = useState<string | null>(null);
  const latestRequest = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const requestId = ++latestRequest.current;
    const params = buildAdoptionInquiryQuery({ page, search, path, status, fromDate, toDate });
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
          throw new Error(`領養意願載入失敗（HTTP ${response.status}）`);
        const nextData = (await response.json()) as ResponseData;
        if (!controller.signal.aborted && requestId === latestRequest.current)
          setData(nextData);
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted && requestId === latestRequest.current)
          setError(
            requestError instanceof Error
              ? requestError.message
              : "領養意願載入失敗",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted && requestId === latestRequest.current)
          setLoading(false);
      });
    return () => controller.abort();
  }, [fromDate, page, path, search, status, toDate]);

  function toggleStatus(inquiry: AdoptionInquiry) {
    const nextStatus: InquiryStatus = inquiry.status === "new" ? "contacted" : "new";
    setUpdatingId(inquiry.id);
    void authFetch(`/v1/management/adoption-inquiries/${inquiry.id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: nextStatus }),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`更新狀態失敗（HTTP ${response.status}）`);
        setData((current) =>
          current
            ? {
                ...current,
                items: current.items.map((item) =>
                  item.id === inquiry.id ? { ...item, status: nextStatus } : item,
                ),
              }
            : current,
        );
      })
      .catch((requestError: unknown) => {
        setError(
          requestError instanceof Error ? requestError.message : "更新狀態失敗",
        );
      })
      .finally(() => setUpdatingId(null));
  }

  return (
    <section aria-labelledby="adoption-inquiries-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">ADOPTION INQUIRY INBOX</span>
          <h1 id="adoption-inquiries-title">領養意願</h1>
          <p>透過 LINE 送出的領養意願表，含問卷回答與 AI 適配度分析。</p>
        </div>
      </div>
      <section className="ui-card ui-card-padded">
        <div className="toolbar" aria-label="領養意願篩選">
          <Field>
            <label htmlFor="inquiry-search">搜尋</label>
            <Input
              id="inquiry-search"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              placeholder="動物名稱、收容編號、領養人或電話"
            />
          </Field>
          <Field>
            <label htmlFor="inquiry-path">領養路徑</label>
            <Select
              id="inquiry-path"
              value={path}
              onChange={(event) => {
                setPath(event.target.value);
                setPage(1);
              }}
            >
              <option value="">全部</option>
              <option value="specific_animal">心有所屬</option>
              <option value="recommend_me">推薦名單</option>
            </Select>
          </Field>
          <Field>
            <label htmlFor="inquiry-status">狀態</label>
            <Select
              id="inquiry-status"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setPage(1);
              }}
            >
              <option value="">全部</option>
              <option value="new">未聯繫</option>
              <option value="contacted">已聯繫</option>
            </Select>
          </Field>
          <Field>
            <label htmlFor="inquiry-from">開始日期</label>
            <Input
              id="inquiry-from"
              type="date"
              value={fromDate}
              onChange={(event) => {
                setFromDate(event.target.value);
                setPage(1);
              }}
            />
          </Field>
          <Field>
            <label htmlFor="inquiry-to">結束日期</label>
            <Input
              id="inquiry-to"
              type="date"
              value={toDate}
              onChange={(event) => {
                setToDate(event.target.value);
                setPage(1);
              }}
            />
          </Field>
        </div>
        {loading ? <LoadingState title="正在載入領養意願…" /> : null}
        {permissionDenied ? (
          <PermissionDeniedState description="請切換到已授權收容所，或聯絡收容所管理者。" />
        ) : null}
        {error ? (
          <ErrorState title="無法載入領養意願" description={error} />
        ) : null}
        {!loading && !error && data?.items.length === 0 ? (
          <EmptyState
            title="目前沒有符合條件的領養意願"
            description="調整搜尋或篩選條件後再試。"
          />
        ) : null}
        {!loading && !error && data?.items.length ? (
          <Table>
            <thead>
              <tr>
                <th>送出時間</th>
                <th>動物</th>
                <th>領養人</th>
                <th>路徑</th>
                <th>AI 適配度</th>
                <th>問卷</th>
                <th>狀態</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((inquiry) => (
                <tr key={inquiry.id}>
                  <td style={NOWRAP_STYLE}>
                    {(() => {
                      const { date, time } = formatTimestamp(inquiry.submitted_at);
                      return (
                        <>
                          {date}
                          <br />
                          {time}
                        </>
                      );
                    })()}
                  </td>
                  <td style={NOWRAP_STYLE}>
                    {inquiry.animal_name}
                    {inquiry.shelter_number ? (
                      <>
                        <br />
                        <small className="muted">{inquiry.shelter_number}</small>
                      </>
                    ) : null}
                  </td>
                  <td style={NOWRAP_STYLE}>
                    {inquiry.adopter_name}
                    <br />
                    <small className="muted">{inquiry.phone_number}</small>
                  </td>
                  <td style={NOWRAP_STYLE}>
                    <Badge>{PATH_LABEL[inquiry.path]}</Badge>
                    {inquiry.ai_recommendation_overridden ? (
                      <>
                        <br />
                        <Badge className="ui-badge-danger">選了非推薦</Badge>
                      </>
                    ) : null}
                  </td>
                  <td style={NOWRAP_STYLE}>
                    {inquiry.ai_suitability_score !== null
                      ? `${inquiry.ai_suitability_score}/100`
                      : "—"}
                  </td>
                  <td style={NOWRAP_STYLE}>
                    <button
                      type="button"
                      style={STATUS_ACTION_STYLE}
                      onClick={() => setViewingText(formatAnswers(inquiry.answers_display))}
                    >
                      查看問卷
                    </button>
                  </td>
                  <td style={NOWRAP_STYLE}>
                    <Badge className={inquiry.status === "new" ? "ui-badge-danger" : undefined}>
                      {inquiry.status === "contacted" ? "已聯繫" : "未聯繫"}
                    </Badge>
                  </td>
                  <td style={NOWRAP_STYLE}>
                    <button
                      type="button"
                      style={{
                        ...STATUS_ACTION_STYLE,
                        opacity: updatingId === inquiry.id ? 0.6 : 1,
                      }}
                      disabled={updatingId === inquiry.id}
                      onClick={() => toggleStatus(inquiry)}
                    >
                      {inquiry.status === "contacted" ? "標記未聯繫" : "標記已聯繫"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : null}
        {data && data.total > data.page_size ? (
          <div className="toolbar pagination">
            <Button
              variant="secondary"
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((value) => value - 1)}
            >
              上一頁
            </Button>
            <span className="muted">
              第 {data.page} 頁，共 {data.total} 筆
            </span>
            <Button
              variant="secondary"
              type="button"
              disabled={page * data.page_size >= data.total}
              onClick={() => setPage((value) => value + 1)}
            >
              下一頁
            </Button>
          </div>
        ) : null}
      </section>
      <Dialog
        open={viewingText !== null}
        title="完整內容"
        onClose={() => setViewingText(null)}
      >
        <p style={{ whiteSpace: "pre-wrap" }}>{viewingText}</p>
      </Dialog>
    </section>
  );
}
