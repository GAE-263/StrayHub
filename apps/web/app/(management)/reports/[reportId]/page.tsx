"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Breadcrumbs } from "../../../../components/management/Breadcrumbs";
import { authFetch } from "../../../../lib/auth";
import {
  ErrorState,
  LoadingState,
} from "../../../../components/management/StateViews";

type Props = { params: Promise<{ reportId: string }> };
type Observation = {
  id: string;
  status: string;
  source_type: string;
  failure_reason?: string | null;
  raw_ai_output?: unknown;
  validated_ai_observation?: unknown;
  human_review_result?: unknown;
};
type Report = {
  id: string;
  animal_id: string;
  animal_name: string | null;
  status: string;
  submitted_at: string;
  answers: Record<string, unknown>;
  note: string | null;
  media_ids: string[];
  ai_observations: Observation[];
};

export default function ReportDetailPage({ params }: Props) {
  const { reportId } = use(params);
  const router = useRouter();
  const [report, setReport] = useState<Report | null>(null);
  const [correction, setCorrection] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => {
    void authFetch(`/v1/management/reports/${reportId}`)
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`回報 Detail 載入失敗（HTTP ${response.status}）`);
        const data = (await response.json()) as { report: Report };
        setReport(data.report);
        setCorrection(JSON.stringify(data.report.answers, null, 2));
      })
      .catch((requestError: unknown) =>
        setError(
          requestError instanceof Error
            ? requestError.message
            : "回報 Detail 載入失敗",
        ),
      );
  };

  useEffect(load, [reportId]);

  const mutate = async (path: string, body: Record<string, unknown>) => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await authFetch(
        `/v1/management/reports/${reportId}/${path}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      if (!response.ok) throw new Error(`操作失敗（HTTP ${response.status}）`);
      setMessage("操作已完成，原始內容與 Audit 仍保留。 ");
      load();
    } catch (requestError: unknown) {
      setError(
        requestError instanceof Error ? requestError.message : "操作失敗",
      );
    } finally {
      setBusy(false);
    }
  };

  if (error && !report)
    return (
      <main>
        <ErrorState title="無法載入回報 Detail" description={error} />
      </main>
    );
  if (!report)
    return (
      <main>
        <LoadingState title="正在載入回報 Detail…" />
      </main>
    );

  return (
    <main aria-labelledby="report-detail-title">
      <Breadcrumbs
        items={[
          { label: "回報收件匣", href: "/reports" },
          { label: report.id.slice(0, 8) },
        ]}
      />
      <div className="page-heading">
        <div>
          <span className="eyebrow">REPORT DETAIL</span>
          <h1 id="report-detail-title">{report.animal_name ?? "動物回報"}</h1>
          <p>
            {new Date(report.submitted_at).toLocaleString("zh-TW")} ·{" "}
            <span className="badge">{report.status}</span>
          </p>
        </div>
      </div>
      {message ? (
        <p className="notice success" role="status">
          {message}
        </p>
      ) : null}
      {error ? (
        <p className="notice error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="content-grid">
        <section className="panel">
          <h2>原始回報</h2>
          <pre className="json-view">
            {JSON.stringify(report.answers, null, 2)}
          </pre>
          <h3>志工心得</h3>
          <p className="preserved-note">{report.note || "未填寫心得"}</p>
          <h3>照片</h3>
          <p className="muted">
            {report.media_ids.length
              ? `${report.media_ids.length} 個 Media Asset，需依權限取得 Signed URL。`
              : "此回報沒有照片。"}
          </p>
        </section>
        <section className="panel">
          <h2>AI 狀態</h2>
          {report.ai_observations.length ? (
            report.ai_observations.map((observation) => (
              <article className="ai-card" key={observation.id}>
                <div>
                  <strong>{observation.source_type}</strong>
                  <span className="badge">{observation.status}</span>
                </div>
                {observation.failure_reason ? (
                  <p className="muted">{observation.failure_reason}</p>
                ) : null}
                <details>
                  <summary>查看 AI 原始／驗證資料</summary>
                  <pre className="json-view">
                    {JSON.stringify(
                      {
                        raw: observation.raw_ai_output,
                        validated: observation.validated_ai_observation,
                        human: observation.human_review_result,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </article>
            ))
          ) : (
            <p className="muted">尚無 AI Observation。</p>
          )}
        </section>
      </div>
      <section className="panel mutation-panel">
        <h2>Correction／Archive</h2>
        <p className="muted">
          修正會建立 Correction 與 Audit；封存只改變狀態，不會 Hard Delete。
        </p>
        <div className="field">
          <label htmlFor="correction-answers">修正後 answers（JSON）</label>
          <textarea
            id="correction-answers"
            value={correction}
            onChange={(event) => setCorrection(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="correction-reason">原因</label>
          <textarea
            id="correction-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="請說明此次修正或封存原因"
          />
        </div>
        <div className="toolbar">
          <button
            className="button"
            type="button"
            disabled={busy || !reason.trim()}
            onClick={() => {
              try {
                void mutate("correction", {
                  reason,
                  observations: JSON.parse(correction),
                });
              } catch {
                setError("修正內容不是有效 JSON");
              }
            }}
          >
            保存 Correction
          </button>
          <button
            className="button button-secondary"
            type="button"
            disabled={busy || !reason.trim()}
            onClick={() => void mutate("archive", { reason })}
          >
            Archive
          </button>
          <button
            className="button button-secondary"
            type="button"
            onClick={() => router.push(`/animals/${report.animal_id}/timeline`)}
          >
            回到 Timeline
          </button>
        </div>
      </section>
    </main>
  );
}
