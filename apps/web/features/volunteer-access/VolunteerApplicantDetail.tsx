"use client";

import React, { useEffect, useRef, useState } from "react";

import { Alert } from "../../components/ui/alert";
import { Dialog } from "../../components/ui/dialog";
import { authFetch } from "../../lib/auth";
import {
  VolunteerServiceSummary,
  type ServiceSummaryItem,
} from "./VolunteerServiceSummary";

type ServiceDate = {
  service_date: string;
  status: string;
  decided_at: string | null;
  decision_reason: string | null;
  version: number;
};

type ApplicationDetail = {
  id: string;
  organization_id: string;
  display_name: string;
  status: string;
  submitted_at: string;
  decided_at: string | null;
  decision_reason: string | null;
  version: number;
  service_dates: ServiceDate[];
};

type RevealedProfile = {
  applicant_name: string;
  phone_number: string;
  basic_profile: Record<string, string> | null;
};

export function VolunteerApplicantDetail({
  organizationId,
  applicationId,
  open,
  onClose,
}: {
  organizationId: string;
  applicationId: string | null;
  open: boolean;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [revealed, setRevealed] = useState<RevealedProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [revealing, setRevealing] = useState(false);
  const [error, setError] = useState("");
  const [revealError, setRevealError] = useState("");
  const [summaryLoaded, setSummaryLoaded] = useState(false);
  const [summaryItems, setSummaryItems] = useState<ServiceSummaryItem[]>([]);
  const [summaryCursor, setSummaryCursor] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState("");
  const requestGeneration = useRef(0);

  useEffect(() => {
    if (!open || !applicationId || !organizationId) return;
    const generation = ++requestGeneration.current;
    setDetail(null);
    setRevealed(null);
    setError("");
    setRevealError("");
    setSummaryLoaded(false);
    setSummaryItems([]);
    setSummaryCursor(null);
    setSummaryError("");
    setSummaryLoading(false);
    setLoading(true);
    setRevealing(true);
    void (async () => {
      try {
        const response = await authFetch(
          `/v1/organizations/${organizationId}/volunteer-applications/${applicationId}`,
        );
        if (!response.ok) throw new Error("無法載入申請人遮罩資料");
        const value = (await response.json()) as ApplicationDetail;
        if (generation === requestGeneration.current) setDetail(value);
      } catch (loadError) {
        if (generation === requestGeneration.current) {
          setError(loadError instanceof Error ? loadError.message : "載入失敗");
        }
      } finally {
        if (generation === requestGeneration.current) setLoading(false);
      }
    })();
    void (async () => {
      try {
        const response = await authFetch(
          `/v1/organizations/${organizationId}/volunteer-applications/${applicationId}/pii-reveal`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ purpose_code: "application_review" }),
          },
        );
        if (!response.ok) throw new Error("目前無法查看申請人資料");
        const value = (await response.json()) as RevealedProfile;
        if (generation === requestGeneration.current) setRevealed(value);
      } catch {
        if (generation === requestGeneration.current) {
          setRevealError("目前無法查看申請人資料，請稍後再試。");
        }
      } finally {
        if (generation === requestGeneration.current) setRevealing(false);
      }
    })();
  }, [applicationId, open, organizationId]);

  function close() {
    requestGeneration.current += 1;
    setDetail(null);
    setRevealed(null);
    setError("");
    setRevealError("");
    setSummaryLoaded(false);
    setSummaryItems([]);
    setSummaryCursor(null);
    setSummaryError("");
    setSummaryLoading(false);
    setLoading(false);
    setRevealing(false);
    onClose();
  }

  async function loadSummary(cursor: string | null = null) {
    if (!applicationId || !organizationId) return;
    const generation = requestGeneration.current;
    setSummaryLoaded(true);
    setSummaryError("");
    setSummaryLoading(true);
    try {
      const query = new URLSearchParams({
        purpose_code: "volunteer_service_history_review",
        limit: "50",
      });
      if (cursor) query.set("cursor", cursor);
      const response = await authFetch(
        `/v1/organizations/${organizationId}/volunteer-applications/${applicationId}/service-summary?${query.toString()}`,
      );
      if (!response.ok) throw new Error("目前無法載入跨收容所服務紀錄");
      const value = (await response.json()) as {
        items: ServiceSummaryItem[];
        next_cursor: string | null;
      };
      if (generation !== requestGeneration.current) return;
      setSummaryItems((current) =>
        cursor ? [...current, ...value.items] : value.items,
      );
      setSummaryCursor(value.next_cursor);
    } catch (summaryFailure) {
      if (generation === requestGeneration.current) {
        setSummaryError(
          summaryFailure instanceof Error
            ? summaryFailure.message
            : "服務紀錄載入失敗",
        );
      }
    } finally {
      if (generation === requestGeneration.current) setSummaryLoading(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="申請人資料"
      onClose={close}
      closeLabel="關閉申請人資料"
    >
      {loading ? <p role="status">正在載入申請資料…</p> : null}
      {error ? <Alert role="alert">{error}</Alert> : null}
      {detail ? (
        <div className="space-y-3">
          <p>
            審核身份：<strong>{detail.display_name}</strong>
          </p>
          <p>申請狀態：{detail.status}</p>
          <p>
            送出時間：{new Date(detail.submitted_at).toLocaleString("zh-TW")}
          </p>
          <div>
            <h3>服務日期</h3>
            <ul>
              {detail.service_dates.length ? (
                detail.service_dates.map((item) => (
                  <li key={item.service_date}>
                    {item.service_date}：{item.status}
                  </li>
                ))
              ) : (
                <li>未指定服務日期</li>
              )}
            </ul>
          </div>
          <section aria-labelledby="applicant-information-title">
            <h3 id="applicant-information-title">申請人資料</h3>
            <p className="muted">
              申請人資料僅供本次審核使用，查看紀錄將留存。
            </p>
            {revealing ? <p role="status">正在載入申請人資料…</p> : null}
            {revealError ? <Alert role="alert">{revealError}</Alert> : null}
            {revealed ? (
              <div>
                <p>姓名：{revealed.applicant_name}</p>
                <p>電話：{revealed.phone_number}</p>
                {revealed.basic_profile?.experience ? (
                  <p>照護經驗：{revealed.basic_profile.experience}</p>
                ) : null}
              </div>
            ) : null}
          </section>
          <VolunteerServiceSummary
            loaded={summaryLoaded}
            items={summaryItems}
            nextCursor={summaryCursor}
            loading={summaryLoading}
            error={summaryError}
            onLoad={() => void loadSummary()}
            onLoadMore={() => void loadSummary(summaryCursor)}
          />
        </div>
      ) : null}
    </Dialog>
  );
}
