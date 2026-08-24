"use client";

import React, { useEffect, useRef, useState } from "react";

import { Alert } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Dialog } from "../../components/ui/dialog";
import { authFetch } from "../../lib/auth";

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
  const requestGeneration = useRef(0);

  useEffect(() => {
    if (!open || !applicationId || !organizationId) return;
    const generation = ++requestGeneration.current;
    setDetail(null);
    setRevealed(null);
    setError("");
    setRevealError("");
    setLoading(true);
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
  }, [applicationId, open, organizationId]);

  function close() {
    requestGeneration.current += 1;
    setDetail(null);
    setRevealed(null);
    setError("");
    setRevealError("");
    setLoading(false);
    setRevealing(false);
    onClose();
  }

  async function reveal() {
    if (!applicationId || !organizationId) return;
    setRevealed(null);
    setRevealError("");
    setRevealing(true);
    try {
      const response = await authFetch(
        `/v1/organizations/${organizationId}/volunteer-applications/${applicationId}/pii-reveal`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ purpose_code: "application_review" }),
        },
      );
      if (!response.ok) throw new Error("目前無法揭露申請人資料");
      setRevealed((await response.json()) as RevealedProfile);
    } catch (revealFailure) {
      setRevealError(
        revealFailure instanceof Error ? revealFailure.message : "揭露失敗",
      );
    } finally {
      setRevealing(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="申請人資料"
      onClose={close}
      closeLabel="關閉申請人資料"
    >
      {loading ? <p role="status">載入遮罩資料中…</p> : null}
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
          <p>申請人姓名與電話需為本次申請審核明確揭露。</p>
          <Button
            type="button"
            onClick={() => void reveal()}
            disabled={revealing}
          >
            {revealing ? "揭露中…" : "申請審核用途揭露"}
          </Button>
          {revealError ? <Alert role="alert">{revealError}</Alert> : null}
          {revealed ? (
            <div role="status">
              <p>姓名：{revealed.applicant_name}</p>
              <p>電話：{revealed.phone_number}</p>
              {revealed.basic_profile?.experience ? (
                <p>照護經驗：{revealed.basic_profile.experience}</p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </Dialog>
  );
}
