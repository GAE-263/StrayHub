"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Breadcrumbs } from "../../../../components/management/Breadcrumbs";
import { authFetch } from "../../../../lib/auth";
import {
  ErrorState,
  LoadingState,
} from "../../../../components/management/StateViews";
import { statusLabel } from "../../../../components/management/ui-status";
import { Badge } from "../../../../components/ui/badge";
import { Button } from "../../../../components/ui/button";
import { Card } from "../../../../components/ui/card";
import { Field } from "../../../../components/ui/field";
import { Textarea } from "../../../../components/ui/textarea";
import { AlertDialog } from "../../../../components/ui/alert-dialog";
import { reportAIStatusSummary } from "../../report-detail-state";

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
  const [archiveOpen, setArchiveOpen] = useState(false);

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
      <div>
        <ErrorState title="無法載入回報 Detail" description={error} />
      </div>
    );
  if (!report)
    return (
      <div>
        <LoadingState title="正在載入回報 Detail…" />
      </div>
    );

  return (
    <section aria-labelledby="report-detail-title">
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
            <Badge>{statusLabel(report.status)}</Badge>
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
        <Card className="ui-card-padded">
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
        </Card>
        <Card className="ui-card-padded">
          <h2>AI 狀態</h2>
          <p role="status" aria-live="polite" aria-atomic="true">
            {reportAIStatusSummary(report.ai_observations)
              .map((item) => `AI：${item.label}`)
              .join("；") || "AI：尚無 AI Observation"}
          </p>
          {report.ai_observations.length ? (
            report.ai_observations.map((observation) => (
              <Card className="ai-card" key={observation.id}>
                <div>
                  <strong>{observation.source_type}</strong>
                  <Badge>{statusLabel(observation.status)}</Badge>
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
              </Card>
            ))
          ) : (
            <p className="muted">尚無 AI Observation。</p>
          )}
        </Card>
      </div>
      <Card className="panel mutation-panel">
        <h2>Correction／Archive</h2>
        <p className="muted">
          修正會建立 Correction 與 Audit；封存只改變狀態，不會 Hard Delete。
        </p>
        <Field>
          <label htmlFor="correction-answers">修正後 answers（JSON）</label>
          <Textarea
            id="correction-answers"
            value={correction}
            onChange={(event) => setCorrection(event.target.value)}
          />
        </Field>
        <Field>
          <label htmlFor="correction-reason">原因</label>
          <Textarea
            id="correction-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="請說明此次修正或封存原因"
          />
        </Field>
        <div className="toolbar">
          <Button
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
          </Button>
          <Button
            variant="secondary"
            type="button"
            disabled={busy || !reason.trim()}
            onClick={() => setArchiveOpen(true)}
          >
            Archive
          </Button>
          <Button
            variant="secondary"
            type="button"
            onClick={() => router.push(`/animals/${report.animal_id}/timeline`)}
          >
            回到 Timeline
          </Button>
        </div>
      </Card>
      <AlertDialog
        open={archiveOpen}
        title="確認封存回報"
        onClose={() => setArchiveOpen(false)}
      >
        <p>封存只會改變回報狀態，不會刪除原始回報、照片或 Audit 紀錄。</p>
        <div className="toolbar">
          <Button
            variant="secondary"
            type="button"
            onClick={() => setArchiveOpen(false)}
          >
            取消
          </Button>
          <Button
            variant="destructive"
            type="button"
            onClick={() => {
              setArchiveOpen(false);
              void mutate("archive", { reason });
            }}
          >
            確認封存
          </Button>
        </div>
      </AlertDialog>
    </section>
  );
}
