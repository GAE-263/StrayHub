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
import { buildGrowthDiaryQuery } from "../management-query";

type Mood = "positive" | "neutral" | "concern" | null;
type EntryStatus = "new" | "reviewed";

type GrowthDiaryEntry = {
  id: string;
  animal_id: string;
  animal_name: string | null;
  shelter_number: string | null;
  // 一篇日記可能是好幾則同一天分享的訊息合併而成，所以是好幾張照片，不是一張。
  photo_urls: string[];
  note: string | null;
  ai_mood: Mood;
  ai_reply: string | null;
  ai_staff_summary: string | null;
  status: EntryStatus;
  created_at: string;
};

type ResponseData = {
  items: GrowthDiaryEntry[];
  page: number;
  page_size: number;
  total: number;
};

const MOOD_LABEL: Record<string, string> = {
  positive: "適應良好",
  neutral: "例行回報",
  concern: "需留意",
};

function moodLabel(mood: Mood): string {
  return mood ? (MOOD_LABEL[mood] ?? mood) : "AI 尚未分析";
}

// 內容／AI 摘要都是不限長度的自由文字——單行截斷＋點擊看完整內容，不然一篇
// 長日記會把整列其他欄位（心情 badge、狀態、操作按鈕）都擠壓到逐字換行。
// 200px 大約是中文全形字 14 個左右，剛好一行放得下重點。
const TRUNCATE_STYLE: CSSProperties = {
  background: "none",
  border: "none",
  color: "inherit",
  cursor: "pointer",
  display: "block",
  font: "inherit",
  maxWidth: 200,
  overflow: "hidden",
  padding: 0,
  textAlign: "left",
  textDecoration: "underline",
  textDecorationStyle: "dotted",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const NOWRAP_STYLE: CSSProperties = { whiteSpace: "nowrap" };
// 「操作」跟旁邊「狀態」的 badge 放在一起，用一般 <Button> 尺寸（44px 高、
// 較大 padding）視覺上會比 badge 大一截——改成跟 .ui-badge 同樣大小的
// 可點擊小按鈕，只是多了 cursor/底線提示可以點。
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

function TruncatedText({
  text,
  onExpand,
}: {
  text: string;
  onExpand: (text: string) => void;
}) {
  return (
    <button type="button" style={TRUNCATE_STYLE} onClick={() => onExpand(text)}>
      {text}
    </button>
  );
}

const CONTENT_THUMBNAIL_STYLE: CSSProperties = {
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  display: "block",
  height: 48,
  objectFit: "cover",
  padding: 0,
  width: 48,
};

const PHOTO_THUMBNAIL_BUTTON_STYLE: CSSProperties = {
  background: "none",
  border: "none",
  flexShrink: 0,
  padding: 0,
  position: "relative",
};

// Overlaid on the 3rd thumbnail when a day's entry has more photos than fit
// inline — "+N" rather than rendering every photo, so one very chatty day
// doesn't blow out the row height.
const PHOTO_COUNT_BADGE_STYLE: CSSProperties = {
  alignItems: "center",
  background: "rgba(0, 0, 0, 0.6)",
  borderRadius: 6,
  bottom: 0,
  color: "#fff",
  display: "flex",
  fontSize: 11,
  fontWeight: 700,
  inset: 0,
  justifyContent: "center",
  position: "absolute",
};

function formatEntryTimestamp(iso: string): { date: string; time: string } {
  const value = new Date(iso);
  return {
    date: value.toLocaleDateString("zh-TW"),
    time: value.toLocaleTimeString("zh-TW"),
  };
}

export default function GrowthDiaryPage() {
  const [search, setSearch] = useState("");
  const [mood, setMood] = useState("");
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
  const [viewingPhoto, setViewingPhoto] = useState<string | null>(null);
  const latestRequest = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const requestId = ++latestRequest.current;
    const params = buildGrowthDiaryQuery({
      page,
      search,
      mood,
      status,
      fromDate,
      toDate,
    });
    setLoading(true);
    setError("");
    setPermissionDenied(false);
    void authFetch(`/v1/management/growth-diary-entries?${params}`, {
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
          throw new Error(`毛孩日記載入失敗（HTTP ${response.status}）`);
        const nextData = (await response.json()) as ResponseData;
        if (!controller.signal.aborted && requestId === latestRequest.current)
          setData(nextData);
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted && requestId === latestRequest.current)
          setError(
            requestError instanceof Error
              ? requestError.message
              : "毛孩日記載入失敗",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted && requestId === latestRequest.current)
          setLoading(false);
      });
    return () => controller.abort();
  }, [fromDate, mood, page, search, status, toDate]);

  function toggleStatus(entry: GrowthDiaryEntry) {
    const nextStatus: EntryStatus = entry.status === "new" ? "reviewed" : "new";
    setUpdatingId(entry.id);
    void authFetch(`/v1/management/growth-diary-entries/${entry.id}/status`, {
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
                  item.id === entry.id ? { ...item, status: nextStatus } : item,
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
    <section aria-labelledby="growth-diary-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">GROWTH DIARY INBOX</span>
          <h1 id="growth-diary-title">毛孩日記</h1>
          <p>領養後的近況分享，含 AI 心情分類與工作人員觀察摘要。</p>
        </div>
      </div>
      <section className="ui-card ui-card-padded">
        <div className="toolbar" aria-label="毛孩日記篩選">
          <Field>
            <label htmlFor="diary-search">搜尋</label>
            <Input
              id="diary-search"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              placeholder="動物名稱、收容編號或內容"
            />
          </Field>
          <Field>
            <label htmlFor="diary-mood">AI 心情</label>
            <Select
              id="diary-mood"
              value={mood}
              onChange={(event) => {
                setMood(event.target.value);
                setPage(1);
              }}
            >
              <option value="">全部</option>
              <option value="positive">適應良好</option>
              <option value="neutral">例行回報</option>
              <option value="concern">需留意</option>
            </Select>
          </Field>
          <Field>
            <label htmlFor="diary-status">狀態</label>
            <Select
              id="diary-status"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setPage(1);
              }}
            >
              <option value="">全部</option>
              <option value="new">未讀</option>
              <option value="reviewed">已讀</option>
            </Select>
          </Field>
          <Field>
            <label htmlFor="diary-from">開始日期</label>
            <Input
              id="diary-from"
              type="date"
              value={fromDate}
              onChange={(event) => {
                setFromDate(event.target.value);
                setPage(1);
              }}
            />
          </Field>
          <Field>
            <label htmlFor="diary-to">結束日期</label>
            <Input
              id="diary-to"
              type="date"
              value={toDate}
              onChange={(event) => {
                setToDate(event.target.value);
                setPage(1);
              }}
            />
          </Field>
        </div>
        {loading ? <LoadingState title="正在載入毛孩日記…" /> : null}
        {permissionDenied ? (
          <PermissionDeniedState description="請切換到已授權收容所，或聯絡收容所管理者。" />
        ) : null}
        {error ? (
          <ErrorState title="無法載入毛孩日記" description={error} />
        ) : null}
        {!loading && !error && data?.items.length === 0 ? (
          <EmptyState
            title="目前沒有符合條件的日記"
            description="調整搜尋或篩選條件後再試。"
          />
        ) : null}
        {!loading && !error && data?.items.length ? (
          <Table>
            <thead>
              <tr>
                <th>時間</th>
                <th>動物</th>
                <th>內容</th>
                <th>AI 心情</th>
                <th>工作人員摘要</th>
                <th>狀態</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((entry) => (
                <tr key={entry.id}>
                  <td style={NOWRAP_STYLE}>
                    {(() => {
                      const { date, time } = formatEntryTimestamp(entry.created_at);
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
                    {entry.animal_name ?? "未知動物"}
                    {entry.shelter_number ? (
                      <>
                        <br />
                        <small className="muted">{entry.shelter_number}</small>
                      </>
                    ) : null}
                  </td>
                  <td>
                    {entry.photo_urls.length > 0 ? (
                      <div style={{ display: "flex", gap: 4, marginBottom: entry.note ? 6 : 0 }}>
                        {entry.photo_urls.slice(0, 3).map((url, index) => (
                          <button
                            key={url}
                            type="button"
                            style={PHOTO_THUMBNAIL_BUTTON_STYLE}
                            onClick={() => setViewingPhoto(url)}
                          >
                            <img
                              src={url}
                              alt={`${entry.animal_name ?? "毛孩"}的日記照片 ${index + 1}`}
                              style={CONTENT_THUMBNAIL_STYLE}
                            />
                            {index === 2 && entry.photo_urls.length > 3 ? (
                              <span style={PHOTO_COUNT_BADGE_STYLE}>
                                +{entry.photo_urls.length - 3}
                              </span>
                            ) : null}
                          </button>
                        ))}
                      </div>
                    ) : null}
                    {entry.note ? (
                      <TruncatedText text={entry.note} onExpand={setViewingText} />
                    ) : entry.photo_urls.length === 0 ? (
                      "—"
                    ) : null}
                  </td>
                  <td style={NOWRAP_STYLE}>
                    <Badge
                      className={entry.ai_mood === "concern" ? "ui-badge-danger" : undefined}
                    >
                      {moodLabel(entry.ai_mood)}
                    </Badge>
                  </td>
                  <td>
                    <TruncatedText
                      text={entry.ai_staff_summary ?? "AI 尚未分析"}
                      onExpand={setViewingText}
                    />
                  </td>
                  <td style={NOWRAP_STYLE}>
                    <Badge className={entry.status === "new" ? "ui-badge-danger" : undefined}>
                      {entry.status === "reviewed" ? "已讀" : "未讀"}
                    </Badge>
                  </td>
                  <td style={NOWRAP_STYLE}>
                    <button
                      type="button"
                      style={{
                        ...STATUS_ACTION_STYLE,
                        opacity: updatingId === entry.id ? 0.6 : 1,
                      }}
                      disabled={updatingId === entry.id}
                      onClick={() => toggleStatus(entry)}
                    >
                      {entry.status === "reviewed" ? "標記未讀" : "標記已讀"}
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
      <Dialog
        open={viewingPhoto !== null}
        title="日記照片"
        onClose={() => setViewingPhoto(null)}
      >
        {viewingPhoto ? (
          <img src={viewingPhoto} alt="毛孩日記照片" style={{ maxWidth: "100%", borderRadius: 8 }} />
        ) : null}
      </Dialog>
    </section>
  );
}
