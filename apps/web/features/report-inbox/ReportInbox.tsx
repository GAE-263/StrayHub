"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { authFetch } from "../../lib/auth";
import { usePublicManagementProfile } from "../../components/management/ManagementLayout";
import styles from "./reports.module.css";
import { AlertDialog } from "../../components/ui/alert-dialog";
import { Badge } from "../../components/ui/badge";
import { Breadcrumb } from "../../components/ui/breadcrumb";
import { Button } from "../../components/ui/button";
import { Field } from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { Textarea } from "../../components/ui/textarea";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../components/management/StateViews";

type Summary = {
  attention_level: string;
  summary: string;
  evidence: { field: string; quote: string }[];
  uncertainties: string[];
  information_quality: string;
};
type Report = {
  id: string;
  animal_id: string;
  animal_name: string;
  shelter_number_snapshot: string;
  volunteer_label?: string;
  submitted_at: string;
  status: string;
  note: string | null;
  story?: string;
  answers: Record<string, string>;
  answer_rows?: { field: string; label: string; value: string; code: string }[];
  summary?: Summary;
  summary_status?: string;
  review_status?: string;
  review_version?: number;
  review_history?: {
    at: string;
    status: string;
    note: string;
    actor_user_id: string;
    actor_label?: string;
  }[];
  media_ids?: string[];
  can_archive?: boolean;
  correction_options?: { code: string; label: string }[];
  ai_observations?: {
    id: string;
    source_type: string;
    status: string;
    validated_ai_observation?: Summary;
  }[];
};
const attention: Record<string, string> = {
  urgent: "建議優先查看",
  review: "值得留意",
  normal: "一般紀錄",
};
const attentionTone: Record<string, string | undefined> = {
  urgent: styles.badgeUrgent,
  review: styles.badgeReview,
  normal: undefined,
};
const statuses: Record<string, string> = {
  pending: "待確認",
  acknowledged: "已確認",
  follow_up: "需追蹤",
  resolved: "追蹤完成",
};
const titles: Record<string, string> = {
  walk_completion: "散步完成",
  activity: "活動狀況",
  gait: "走路狀況",
  defecation: "排便狀況",
  animal_interaction: "遇到其他動物時",
  appearance_special_status: "外觀／特殊狀態",
  note: "補充說明",
  story: "小故事",
};
const time = (value: string) =>
  new Date(value).toLocaleString("zh-TW", {
    timeZone: "Asia/Taipei",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
async function request(path: string, init?: RequestInit) {
  const response = await authFetch(path, init);
  if (!response.ok)
    throw new Error(
      response.status === 409
        ? "同事可能已更新這筆回報，請重新載入後再操作。"
        : response.status === 403
          ? "目前帳號沒有操作權限。"
          : "無法完成操作，請稍後重試。",
    );
  return response.json();
}

export function ReportInbox() {
  const [data, setData] = useState<{ items: Report[]; total: number }>({
    items: [],
    total: 0,
  });
  const [query, setQuery] = useState("");
  const [lifecycle, setLifecycle] = useState("");
  const [review, setReview] = useState("");
  const [level, setLevel] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    Object.entries({
      query,
      status: lifecycle,
      review_status: review,
      attention_level: level,
      from_date: from,
      to_date: to,
    }).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    const timer = setTimeout(() => {
      request(`/v1/management/reports?${params}`)
        .then((result) => {
          if (active) setData(result);
        })
        .catch(() => {
          if (active) setError("無法載入回報收件匣，請稍後重試。");
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [query, lifecycle, review, level, from, to, page, refresh]);
  return (
    <section className={styles.page} aria-labelledby="reports-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">回報管理</span>
          <h1 id="reports-title">照護回報收件匣</h1>
          <p>查看志工觀察，記下需要接續追蹤的事。</p>
        </div>
        <Button
          type="button"
          variant="secondary"
          onClick={() => setRefresh((x) => x + 1)}
        >
          重新整理
        </Button>
      </div>
      <section className="ui-card ui-card-padded">
        <div className="toolbar" aria-label="回報篩選">
          <Field>
            <label htmlFor="report-query">搜尋動物／收容編號</label>
            <Input
              id="report-query"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(1);
              }}
              placeholder="例如：小黑、A023"
            />
          </Field>
          <Field>
            <label htmlFor="report-lifecycle">資料狀態</label>
            <Select
              id="report-lifecycle"
              value={lifecycle}
              onChange={(e) => {
                setLifecycle(e.target.value);
                setPage(1);
              }}
            >
              <option value="">全部</option>
              <option value="saved">已送出</option>
              <option value="amended">已更正</option>
              <option value="archived">已封存</option>
            </Select>
          </Field>
          <Field>
            <label htmlFor="report-review">處理狀態</label>
            <Select
              id="report-review"
              value={review}
              onChange={(e) => {
                setReview(e.target.value);
                setPage(1);
              }}
            >
              <option value="">全部</option>
              {Object.entries(statuses).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field>
            <label htmlFor="report-level">留意程度</label>
            <Select
              id="report-level"
              value={level}
              onChange={(e) => {
                setLevel(e.target.value);
                setPage(1);
              }}
            >
              <option value="">全部</option>
              {Object.entries(attention).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field>
            <label htmlFor="report-from">開始日期</label>
            <Input
              id="report-from"
              type="date"
              value={from}
              onChange={(e) => {
                setFrom(e.target.value);
                setPage(1);
              }}
            />
          </Field>
          <Field>
            <label htmlFor="report-to">結束日期</label>
            <Input
              id="report-to"
              type="date"
              value={to}
              onChange={(e) => {
                setTo(e.target.value);
                setPage(1);
              }}
            />
          </Field>
        </div>
        <p className="muted">
          優先列出待確認及需追蹤回報。時間以台灣時間顯示。
        </p>
        {error ? (
          <ErrorState title={error} />
        ) : loading ? (
          <LoadingState title="正在載入回報…" />
        ) : !data.items.length ? (
          <EmptyState
            title="找不到符合條件的回報"
            description="請調整篩選條件。"
          />
        ) : (
          <div className="stack-sm">
            {data.items.map((report) => (
              <Link
                className={`list-card ${styles.row}`}
                href={`/reports/${report.id}`}
                key={report.id}
              >
                <div>
                  <Badge className={attentionTone[report.summary?.attention_level || "normal"]}>
                    {attention[report.summary?.attention_level || "normal"]}
                  </Badge>
                  <h2>
                    {report.animal_name || "動物回報"}{" "}
                    <small className="muted">
                      {report.shelter_number_snapshot}
                    </small>
                  </h2>
                </div>
                <div>
                  {report.summary_status === "succeeded" ? (
                    <p>{report.summary?.summary || "查看完整志工回報"}</p>
                  ) : report.summary?.evidence?.length ? (
                    <ul
                      className={`${styles.evidenceChips} ${styles.evidenceChipsCompact}`}
                    >
                      {report.summary.evidence.map((e, i) => (
                        <li key={i} className={styles.evidenceChip}>
                          <span className={styles.chipKey}>
                            {titles[e.field] || "觀察"}
                          </span>
                          <span className={styles.chipValue}>{e.quote}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>{report.summary?.summary || "查看完整志工回報"}</p>
                  )}
                  <small className="muted">
                    {report.summary_status === "succeeded"
                      ? "AI 初步整理"
                      : "固定回答整理"}{" "}
                    · {report.volunteer_label || "志工"} ·{" "}
                    {time(report.submitted_at)}
                  </small>
                  {report.summary?.information_quality === "conflicting" && (
                    <p>描述有出入，請確認原文</p>
                  )}
                  {report.summary?.information_quality === "insufficient" && (
                    <p>部分資訊待確認</p>
                  )}
                </div>
                <strong>{statuses[report.review_status || "pending"]}　→</strong>
              </Link>
            ))}
          </div>
        )}
        <div className="toolbar pagination">
          <Button
            type="button"
            variant="secondary"
            disabled={page === 1 || loading}
            onClick={() => setPage((p) => p - 1)}
          >
            上一頁
          </Button>
          <span className="muted">
            第 {page} 頁 · 共 {data.total} 筆
          </span>
          <Button
            type="button"
            variant="secondary"
            disabled={page * 20 >= data.total || loading}
            onClick={() => setPage((p) => p + 1)}
          >
            下一頁
          </Button>
        </div>
      </section>
    </section>
  );
}

function ReportPhoto({ id, index }: { id: string; index: number }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setError(false);
    request(`/v1/media/${id}/download-url`, { method: "POST" })
      .then((data) => {
        if (active) setUrl(data.url);
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [id, retry]);
  return error ? (
    <Button type="button" variant="secondary" onClick={() => setRetry((x) => x + 1)}>
      照片 {index + 1} 載入失敗，重新載入
    </Button>
  ) : url ? (
    <a href={url} target="_blank" rel="noreferrer">
      <img
        src={url}
        alt={`志工回報照片 ${index + 1}，點選放大`}
        onError={() => setError(true)}
      />
    </a>
  ) : (
    <p>照片載入中…</p>
  );
}

export function ReportDetail({ id }: { id: string }) {
  const [report, setReport] = useState<Report | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [corrected, setCorrected] = useState("");
  const [revision, setRevision] = useState(0);
  const [editAnswers, setEditAnswers] = useState<Record<string, string>>({});
  const [editNote, setEditNote] = useState("");
  const [editReason, setEditReason] = useState("");
  const [archiveOpen, setArchiveOpen] = useState(false);
  const profile = usePublicManagementProfile();
  useEffect(() => {
    let active = true;
    setReport(null);
    setError("");
    request(`/v1/management/reports/${id}`)
      .then((data) => {
        if (active) {
          setReport(data.report);
          setCorrected(data.report.summary?.summary || "");
          setEditAnswers(data.report.answers);
          setEditNote(data.report.note || "");
        }
      })
      .catch(() => {
        if (active) setError("無法載入回報詳情，請稍後重試。");
      });
    return () => {
      active = false;
    };
  }, [id, revision]);
  const mutate = async (path: string, body: unknown, success: string) => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await request(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setMessage(success);
      setNote("");
      setReason("");
      setRevision((x) => x + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失敗");
    } finally {
      setBusy(false);
    }
  };
  if (!report)
    return (
      <section aria-labelledby="report-detail-loading">
        {error ? (
          <ErrorState title={error} />
        ) : (
          <LoadingState title="正在載入回報…" />
        )}
        <Button type="button" variant="secondary" onClick={() => setRevision((x) => x + 1)}>
          重新載入
        </Button>
      </section>
    );
  const summary = report.summary;
  const status = report.review_status || "pending";
  const observation = report.ai_observations?.find(
    (o) => o.source_type === "care_report_summary",
  );
  const pendingObservation = report.ai_observations?.find((o) =>
    ["pending", "pending_enqueue", "retry_wait", "running"].includes(o.status),
  );
  const failedObservation = report.ai_observations?.find(
    (o) => o.status === "failed",
  );
  return (
    <section className={styles.page}>
      <Breadcrumb>
        <Link href="/reports">回報收件匣</Link>
        <span> ／ 回報詳情</span>
      </Breadcrumb>
      <div className="page-heading">
        <div>
          <span className="eyebrow">回報詳情</span>
          <h1>
            {report.animal_name} <small className="muted">{report.shelter_number_snapshot}</small>
          </h1>
          <p>
            {report.volunteer_label || "志工"} · {time(report.submitted_at)}
          </p>
        </div>
        <Link className="text-link" href={`/animals/${report.animal_id}/timeline`}>
          查看動物近期歷程 →
        </Link>
      </div>
      <div className={styles.actions}>
        <Link className="text-link" href={`/animals/${report.animal_id}`}>
          查看動物檔案
        </Link>
        <Button type="button" variant="secondary" onClick={() => setRevision((x) => x + 1)}>
          重新載入回報
        </Button>
      </div>
      {pendingObservation ? (
        <p role="status" aria-live="polite">
          AI 處理中，完成前仍可查看原始回報。
        </p>
      ) : failedObservation ? (
        <p role="status" aria-live="polite">
          AI 處理失敗；原始回報保留，可稍後重試。
        </p>
      ) : null}
      {report.ai_observations?.some(
        (o) =>
          o.source_type !== "care_report_summary" && o.status === "succeeded",
      ) && (
        <p role="status" aria-live="polite">
          AI 結果需要人工覆核。
          <Link className="text-link" href="/ai-review">
            前往 AI 覆核
          </Link>
        </p>
      )}
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      {message && (
        <div className="notice success" role="status">
          {message}
        </div>
      )}
      <article className="ui-card ui-card-padded">
        <div className="section-heading">
          <h2>
            {report.summary_status === "succeeded"
              ? "AI 初步整理"
              : "固定回答整理"}
          </h2>
          <Badge className={attentionTone[summary?.attention_level || "normal"]}>
            {attention[summary?.attention_level || "normal"]}
          </Badge>
        </div>
        {report.summary_status === "succeeded" ? (
          <p className={styles.summary}>
            {summary?.summary || "尚無整理，請查看原始回報。"}
          </p>
        ) : summary?.evidence?.length ? (
          <ul className={styles.evidenceChips}>
            {summary.evidence.map((e, i) => (
              <li key={i} className={styles.evidenceChip}>
                <span className={styles.chipKey}>
                  {titles[e.field] || "觀察"}
                </span>
                <span className={styles.chipValue}>{e.quote}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.summary}>
            {summary?.summary || "尚無整理，請查看原始回報。"}
          </p>
        )}
        {report.summary_status !== "succeeded" && (
          <p className="muted">
            {report.summary_status === "pending"
              ? "AI 正在整理，可先查看原文與處理回報。"
              : report.summary_status === "stale"
                ? "回報內容已更正，原摘要已停用。"
                : report.summary_status === "rejected"
                  ? "AI 摘要已由工作人員退回，以下依固定回答呈現。"
                  : report.summary_status === "failed"
                    ? "AI 暫時無法完成整理，原始回報已保存。"
                    : "此筆歷史回報尚未進行 AI 整理。"}
          </p>
        )}
        {summary?.information_quality === "conflicting" && (
          <p>描述有出入，請對照原文確認。</p>
        )}
        <div
          className={
            report.summary_status === "succeeded" ? styles.columns : undefined
          }
        >
          {report.summary_status === "succeeded" ? (
            <div>
              <h3>觀察依據</h3>
              {summary?.evidence?.length ? (
                <ul className={styles.evidenceChips}>
                  {summary.evidence.map((e, i) => (
                    <li key={i} className={styles.evidenceChip}>
                      <span className={styles.chipKey}>
                        {titles[e.field] || "觀察"}
                      </span>
                      <span className={styles.chipValue}>{e.quote}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>目前沒有列出特殊觀察依據。</p>
              )}
            </div>
          ) : null}
          <div>
            <h3>待確認事項</h3>
            {summary?.uncertainties?.length ? (
              <ul>
                {summary.uncertainties.map((u, i) => (
                  <li key={i}>{u}</li>
                ))}
              </ul>
            ) : (
              <p>未列出額外待確認事項。</p>
            )}
          </div>
        </div>
        {observation &&
          profile === null &&
          report.summary_status === "succeeded" && (
            <details>
              <summary>覆核 AI 摘要（與照護處理分開）</summary>
              <p>
                覆核結果：
                {{
                  succeeded: "待覆核",
                  confirmed: "已採用",
                  corrected: "已修正",
                  rejected: "已退回",
                }[observation.status] || "待覆核"}
              </p>
              <Field>
                <label htmlFor="ai-review-summary">摘要文字</label>
                <Textarea
                  id="ai-review-summary"
                  value={corrected}
                  onChange={(e) => setCorrected(e.target.value)}
                  maxLength={180}
                />
              </Field>
              <Field>
                <label htmlFor="ai-review-reason">覆核原因</label>
                <Input
                  id="ai-review-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={500}
                />
              </Field>
              <div className={styles.actions}>
                {(
                  [
                    ["confirm", "採用摘要", "default"],
                    ["reject", "退回摘要", "secondary"],
                    ["correct", "保存摘要修正", "secondary"],
                  ] as const
                ).map(([action, label, variant]) => (
                  <Button
                    type="button"
                    variant={variant}
                    disabled={busy || !reason.trim() || !corrected.trim()}
                    key={action}
                    onClick={() =>
                      mutate(
                        `/v1/management/ai-review/${observation.id}/review`,
                        {
                          action,
                          reason,
                          corrected_observation:
                            action === "correct"
                              ? { ...summary, summary: corrected }
                              : undefined,
                        },
                        "AI 覆核已保存；照護處理狀態維持原值。",
                      )
                    }
                  >
                    {label}
                  </Button>
                ))}
              </div>
            </details>
          )}
      </article>
      <article className="ui-card ui-card-padded">
        <h2>
          {report.status === "amended" ? "志工回報（已更正）" : "志工原始回報"}
        </h2>
        <dl className={styles.answers}>
          {report.answer_rows?.map((row) => (
            <div key={row.field}>
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
        <h3>補充說明</h3>
        <p className={styles.original}>{report.note || "未填寫補充說明"}</p>
        <h3>今天的小故事</h3>
        <p className={styles.original}>{report.story || "未填寫小故事"}</p>
        <h3>回報照片</h3>
        <div className={styles.photos}>
          {report.media_ids?.length ? (
            report.media_ids.map((media, i) => (
              <ReportPhoto key={media} id={media} index={i} />
            ))
          ) : (
            <p>此回報沒有照片。</p>
          )}
        </div>
      </article>
      <article className="ui-card ui-card-padded">
        <h2>工作人員處理 · {statuses[status]}</h2>
        <p className="muted">
          「已確認」表示已看過這次回報。需要接續查看時，請記下追蹤事項。
        </p>
        {profile === null && report.status !== "archived" && (
          <>
            <Field>
              <label htmlFor="processing-note">
                處理備註（需追蹤與追蹤完成必填）
              </label>
              <Textarea
                id="processing-note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                maxLength={2000}
                placeholder="例如：已告知照護負責人，下一班留意走路情況。"
              />
            </Field>
            <div className={styles.actions}>
              {(
                [
                  ["acknowledged", "標記已確認"],
                  ["follow_up", "標記需追蹤"],
                  ["resolved", "追蹤完成"],
                ] as const
              ).map(([next, label]) => (
                <Button
                  type="button"
                  variant="secondary"
                  key={next}
                  disabled={
                    busy ||
                    next === status ||
                    (next !== "acknowledged" && !note.trim()) ||
                    (next === "resolved" && status !== "follow_up")
                  }
                  onClick={() =>
                    mutate(
                      `/v1/management/reports/${id}/processing`,
                      {
                        status: next,
                        note,
                        expected_version: report.review_version || 0,
                      },
                      "處理紀錄已保存。",
                    )
                  }
                >
                  {label}
                </Button>
              ))}
            </div>
          </>
        )}
        <h3>處理歷程</h3>
        {report.review_history?.length ? (
          <ol>
            {report.review_history.map((event, i) => (
              <li key={i}>
                <strong>{statuses[event.status] || "重新確認"}</strong> ·{" "}
                {time(event.at)} · {event.actor_label || "工作人員"}
                <p className={styles.original}>{event.note || "未填寫備註"}</p>
              </li>
            ))}
          </ol>
        ) : (
          <p>尚無處理紀錄。</p>
        )}
      </article>
      {profile === null && report.status !== "archived" && (
        <details className={`ui-card ui-card-padded ${styles.correctionPanel}`}>
          <summary>更正回報／封存</summary>
          <p>請填寫更正原因。原始內容與操作紀錄會保留，更正後需重新確認。</p>
          <div className={styles.answers}>
            {report.answer_rows?.map((row) => (
              <Field key={row.field}>
                <label htmlFor={`correction-${row.field}`}>{row.label}</label>
                <Select
                  id={`correction-${row.field}`}
                  value={editAnswers[row.field] || row.code}
                  onChange={(e) =>
                    setEditAnswers((values) => ({
                      ...values,
                      [row.field]: e.target.value,
                    }))
                  }
                >
                  <option value={row.code}>{row.value}</option>
                  {report.correction_options
                    ?.filter(
                      (o) =>
                        o.code !== row.code &&
                        o.code.startsWith(
                          row.field === "appearance_special_status"
                            ? "appearance."
                            : `${row.field}.`,
                        ),
                    )
                    .map((o) => (
                      <option key={o.code} value={o.code}>
                        {o.label}
                      </option>
                    ))}
                  {row.code !== "unobserved" && (
                    <option value="unobserved">今天沒觀察到這項</option>
                  )}
                </Select>
              </Field>
            ))}
          </div>
          <Field>
            <label htmlFor="correction-note">更正補充說明</label>
            <Textarea
              id="correction-note"
              value={editNote}
              onChange={(e) => setEditNote(e.target.value)}
              maxLength={5000}
            />
          </Field>
          <Field>
            <label htmlFor="correction-reason">更正或封存原因</label>
            <Input
              id="correction-reason"
              value={editReason}
              onChange={(e) => setEditReason(e.target.value)}
              maxLength={500}
            />
          </Field>
          <div className={styles.actions}>
            <Button
              type="button"
              disabled={busy || !editReason.trim()}
              onClick={() =>
                mutate(
                  `/v1/management/reports/${id}/correction`,
                  {
                    reason: editReason,
                    observations: editAnswers,
                    note: editNote,
                  },
                  "更正已保存，請重新確認回報。",
                )
              }
            >
              保存更正
            </Button>
            {report.can_archive && (
              <Button
                type="button"
                variant="destructive"
                disabled={busy || !editReason.trim()}
                onClick={() => setArchiveOpen(true)}
              >
                封存回報
              </Button>
            )}
          </div>
        </details>
      )}
      <AlertDialog
        open={archiveOpen}
        title="確認封存回報"
        onClose={() => setArchiveOpen(false)}
      >
        <p>封存會保留回報與歷程，之後無法更新處理狀態。</p>
        <div className="dialog-actions">
          <Button type="button" variant="secondary" onClick={() => setArchiveOpen(false)}>
            取消
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={busy}
            onClick={() => {
              setArchiveOpen(false);
              void mutate(
                `/v1/management/reports/${id}/archive`,
                { reason: editReason },
                "回報已封存。",
              );
            }}
          >
            {busy ? "封存中…" : "確認封存"}
          </Button>
        </div>
      </AlertDialog>
    </section>
  );
}
