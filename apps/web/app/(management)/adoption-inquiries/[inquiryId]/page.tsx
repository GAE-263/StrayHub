"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
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
import { Select } from "../../../../components/ui/select";
import { Textarea } from "../../../../components/ui/textarea";

type Props = { params: Promise<{ inquiryId: string }> };
type AdoptionInquiry = {
  id: string;
  path: string;
  target_animal_id: string;
  animal_name: string | null;
  animal_name_snapshot: string;
  shelter_number_snapshot: string | null;
  answers: Record<string, unknown>;
  // One entry for the specific_animal path (the target animal scored against
  // the adopter's answers), up to a few for recommend_me (ranked candidates).
  match_scores_snapshot:
    | Array<{ animal_id: string; score: number; reasons: string[] }>
    | null;
  adopter_name: string;
  phone_number: string;
  status: string;
  submitted_at: string;
  staff_notes: string | null;
};

const PATH_LABELS: Record<string, string> = {
  specific_animal: "已有目標動物",
  recommend_me: "系統推薦",
};

const ANSWER_LABELS: Record<string, string> = {
  housing_type: "居住環境",
  dog_experience: "養狗經驗",
  other_pets: "家中其他寵物",
  household_members: "家庭成員",
  work_schedule: "作息時間",
  preferred_size: "希望的體型",
  preferred_energy: "希望的活動力",
  parenting_style: "飼養風格",
  patience_level: "耐心與應變",
  adoption_motivation: "領養動機",
  contact_time: "方便聯繫時間",
};

const STATUS_TRANSITIONS: Record<string, string[]> = {
  new: ["contacted", "closed"],
  contacted: ["in_review", "closed"],
  in_review: ["contacted", "closed"],
  closed: [],
};

export default function AdoptionInquiryDetailPage({ params }: Props) {
  const { inquiryId } = use(params);
  const [inquiry, setInquiry] = useState<AdoptionInquiry | null>(null);
  const [nextStatus, setNextStatus] = useState("");
  const [staffNotes, setStaffNotes] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => {
    void authFetch(`/v1/management/adoption-inquiries/${inquiryId}`)
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`領養意願詳情載入失敗（HTTP ${response.status}）`);
        const data = (await response.json()) as { inquiry: AdoptionInquiry };
        setInquiry(data.inquiry);
        setStaffNotes(data.inquiry.staff_notes ?? "");
        setNextStatus(STATUS_TRANSITIONS[data.inquiry.status]?.[0] ?? "");
      })
      .catch((requestError: unknown) =>
        setError(
          requestError instanceof Error
            ? requestError.message
            : "領養意願詳情載入失敗",
        ),
      );
  };

  useEffect(load, [inquiryId]);

  async function updateStatus() {
    if (!nextStatus) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await authFetch(
        `/v1/management/adoption-inquiries/${inquiryId}/status`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            status: nextStatus,
            staff_notes: staffNotes.trim() || null,
          }),
        },
      );
      if (!response.ok) throw new Error(`狀態更新失敗（HTTP ${response.status}）`);
      setMessage("領養意願狀態已更新。");
      load();
    } catch (requestError: unknown) {
      setError(
        requestError instanceof Error ? requestError.message : "狀態更新失敗",
      );
    } finally {
      setBusy(false);
    }
  }

  if (error && !inquiry)
    return (
      <div>
        <ErrorState title="無法載入領養意願詳情" description={error} />
      </div>
    );
  if (!inquiry)
    return (
      <div>
        <LoadingState title="正在載入領養意願詳情…" />
      </div>
    );

  const availableTransitions = STATUS_TRANSITIONS[inquiry.status] ?? [];
  const answerEntries = Object.entries(inquiry.answers).filter(
    ([key]) => !["adopter_name", "phone_number"].includes(key),
  );

  return (
    <section aria-labelledby="adoption-inquiry-detail-title">
      <Breadcrumbs
        items={[
          { label: "領養意願收件匣", href: "/adoption-inquiries" },
          { label: inquiry.id.slice(0, 8) },
        ]}
      />
      <div className="page-heading">
        <div>
          <span className="eyebrow">ADOPTION INQUIRY DETAIL</span>
          <h1 id="adoption-inquiry-detail-title">
            {inquiry.animal_name ?? inquiry.animal_name_snapshot}
          </h1>
          <p>
            {new Date(inquiry.submitted_at).toLocaleString("zh-TW")} ·{" "}
            <Badge>{statusLabel(inquiry.status)}</Badge> ·{" "}
            {PATH_LABELS[inquiry.path] ?? inquiry.path}
          </p>
        </div>
        <Link
          className="ui-button ui-button-default"
          href={`/animals/${inquiry.target_animal_id}`}
        >
          查看動物檔案
        </Link>
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
          <h2>領養人問卷</h2>
          <dl className="detail-list">
            <div>
              <dt>姓名</dt>
              <dd>{inquiry.adopter_name}</dd>
            </div>
            <div>
              <dt>聯絡電話</dt>
              <dd>{inquiry.phone_number}</dd>
            </div>
            {answerEntries.map(([key, value]) => (
              <div key={key}>
                <dt>{ANSWER_LABELS[key] ?? key}</dt>
                <dd>{String(value)}</dd>
              </div>
            ))}
          </dl>
        </Card>
        <Card className="ui-card-padded">
          <h2>媒合資訊</h2>
          {inquiry.match_scores_snapshot ? (
            <pre className="json-view">
              {JSON.stringify(inquiry.match_scores_snapshot, null, 2)}
            </pre>
          ) : (
            <p className="muted">
              此筆為較舊的領養意願，送出當時尚未計算適配分數。
            </p>
          )}
        </Card>
      </div>
      <Card className="panel mutation-panel">
        <h2>處理狀態</h2>
        <p className="muted">
          狀態變更會記錄稽核紀錄；已結案的領養意願無法再變更狀態。
        </p>
        {availableTransitions.length ? (
          <>
            <Field>
              <label htmlFor="inquiry-status">下一個狀態</label>
              <Select
                id="inquiry-status"
                value={nextStatus}
                onChange={(event) => setNextStatus(event.target.value)}
              >
                {availableTransitions.map((option) => (
                  <option key={option} value={option}>
                    {statusLabel(option)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field>
              <label htmlFor="inquiry-staff-notes">工作人員備註</label>
              <Textarea
                id="inquiry-staff-notes"
                value={staffNotes}
                onChange={(event) => setStaffNotes(event.target.value)}
                placeholder="記錄聯絡結果或後續安排"
              />
            </Field>
            <div className="toolbar">
              <Button type="button" disabled={busy} onClick={updateStatus}>
                更新狀態
              </Button>
            </div>
          </>
        ) : (
          <p className="muted">此領養意願已結案。</p>
        )}
      </Card>
    </section>
  );
}
