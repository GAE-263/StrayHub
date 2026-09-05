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
import { Input } from "../../../../components/ui/input";
import { Select } from "../../../../components/ui/select";
import { Textarea } from "../../../../components/ui/textarea";
import { AlertDialog } from "../../../../components/ui/alert-dialog";
import {
  canMutateReport,
  reportAIStatusSummary,
} from "../../report-detail-state";
import {
  EMPTY_VOCABULARY,
  buildVocabulary,
  correctionOptions,
  describeAnswers,
  type AnswerSnapshot,
  type ObservationCategoryItem,
  type ObservationOptionItem,
  type Vocabulary,
} from "../../report-answers";
import { usePublicManagementProfile } from "../../../../components/management/ManagementLayout";

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
  answer_snapshots?: Record<string, AnswerSnapshot> | null;
  note: string | null;
  media_ids: string[];
  ai_observations: Observation[];
};

export default function ReportDetailPage({ params }: Props) {
  const { reportId } = use(params);
  const router = useRouter();
  const publicManagementProfile = usePublicManagementProfile();
  const [report, setReport] = useState<Report | null>(null);
  const [vocabulary, setVocabulary] = useState<Vocabulary>(EMPTY_VOCABULARY);
  const [correction, setCorrection] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);

  const load = () => {
    void authFetch(`/v1/management/reports/${reportId}`)
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`回報詳情載入失敗（HTTP ${response.status}）`);
        const data = (await response.json()) as { report: Report };
        setReport(data.report);
        setCorrection(
          Object.fromEntries(
            Object.entries(data.report.answers ?? {}).map(([key, value]) => [
              key,
              typeof value === "string" ? value : String(value ?? ""),
            ]),
          ),
        );
      })
      .catch((requestError: unknown) =>
        setError(
          requestError instanceof Error
            ? requestError.message
            : "回報詳情載入失敗",
        ),
      );
  };

  useEffect(load, [reportId]);

  useEffect(() => {
    // Labels degrade to snapshots and readable codes, so a vocabulary that
    // fails to load must not block the report itself.
    let active = true;
    void Promise.all([
      authFetch("/v1/observation-categories"),
      authFetch("/v1/observation-options"),
    ])
      .then(async ([categoryResponse, optionResponse]) => {
        if (!categoryResponse.ok || !optionResponse.ok) return;
        const categories = (await categoryResponse.json()) as {
          items: ObservationCategoryItem[];
        };
        const options = (await optionResponse.json()) as {
          items: ObservationOptionItem[];
        };
        if (!active) return;
        setVocabulary(buildVocabulary(categories.items, options.items));
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

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
      setMessage("操作已完成，原始內容與稽核紀錄仍保留。 ");
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
        <ErrorState title="無法載入回報詳情" description={error} />
      </div>
    );
  if (!report)
    return (
      <div>
        <LoadingState title="正在載入回報詳情…" />
      </div>
    );

  const describedAnswers = describeAnswers(
    report.answers,
    report.answer_snapshots,
    vocabulary,
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
          {describedAnswers.length ? (
            <dl className="detail-list">
              {describedAnswers.map((answer) => (
                <div key={answer.key}>
                  <dt>{answer.categoryLabel}</dt>
                  <dd>
                    {answer.valueLabel}
                    {answer.resolved ? null : (
                      <span className="muted answer-code"> {answer.code}</span>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="muted">此回報沒有觀察項目。</p>
          )}
          <h3>志工心得</h3>
          <p className="preserved-note">{report.note || "未填寫心得"}</p>
          <h3>照片</h3>
          <p className="muted">
            {report.media_ids.length
              ? `${report.media_ids.length} 個媒體檔案，需依權限取得簽署網址（Signed URL）。`
              : "此回報沒有照片。"}
          </p>
        </Card>
        <Card className="ui-card-padded">
          <h2>AI 狀態</h2>
          <p role="status" aria-live="polite" aria-atomic="true">
            {reportAIStatusSummary(report.ai_observations)
              .map((item) => `AI：${item.label}`)
              .join("；") || "AI：尚無 AI 觀察結果"}
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
            <p className="muted">尚無 AI 觀察結果。</p>
          )}
        </Card>
      </div>
      {canMutateReport(publicManagementProfile) ? (
        <Card className="panel mutation-panel">
          <h2>修正／封存</h2>
          <p className="muted">
            修正會建立修正紀錄與稽核紀錄；封存只改變狀態，不會永久刪除。
          </p>
          {describedAnswers.length ? (
            describedAnswers.map((answer) => {
              const fieldId = `correction-${answer.key}`;
              const choices = correctionOptions(answer, vocabulary);
              const listed =
                (vocabulary.optionsByCategory[answer.key] ?? []).length > 0;
              const value = correction[answer.key] ?? answer.code;
              const update = (next: string) =>
                setCorrection((current) => ({
                  ...current,
                  [answer.key]: next,
                }));
              return (
                <Field key={answer.key}>
                  <label htmlFor={fieldId}>{answer.categoryLabel}</label>
                  {listed ? (
                    <Select
                      id={fieldId}
                      value={value}
                      onChange={(event) => update(event.target.value)}
                    >
                      {choices.map((choice) => (
                        <option key={choice.code} value={choice.code}>
                          {choice.label}
                        </option>
                      ))}
                    </Select>
                  ) : (
                    <>
                      <Input
                        id={fieldId}
                        value={value}
                        onChange={(event) => update(event.target.value)}
                      />
                      <p className="muted">
                        此項目未在觀察選項設定中，僅能直接編輯代碼。
                      </p>
                    </>
                  )}
                </Field>
              );
            })
          ) : (
            <p className="muted">此回報沒有可修正的觀察項目。</p>
          )}
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
              onClick={() =>
                void mutate("correction", { reason, observations: correction })
              }
            >
              保存修正
            </Button>
            <Button
              variant="secondary"
              type="button"
              disabled={busy || !reason.trim()}
              onClick={() => setArchiveOpen(true)}
            >
              封存
            </Button>
            <Button
              variant="secondary"
              type="button"
              onClick={() =>
                router.push(`/animals/${report.animal_id}/timeline`)
              }
            >
              回到近期歷程
            </Button>
          </div>
        </Card>
      ) : null}
      {canMutateReport(publicManagementProfile) ? (
        <AlertDialog
          open={archiveOpen}
          title="確認封存回報"
          onClose={() => setArchiveOpen(false)}
        >
          <p>封存只會改變回報狀態，不會刪除原始回報、照片或稽核紀錄。</p>
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
      ) : null}
    </section>
  );
}
