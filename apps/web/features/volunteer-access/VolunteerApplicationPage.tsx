"use client";

import React from "react";
import { useEffect, useState } from "react";
import { Alert } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { Checkbox } from "../../components/ui/checkbox";

import {
  formatRemainingDuration,
  formatTaiwanDateTime,
  safeVolunteerError,
  type VolunteerStatus,
} from "./volunteerAccess";

type Props = {
  idToken: string;
  shelterEntryReference: string;
  initialStatus?: VolunteerStatus | null;
};

const STATUS_COPY: Record<string, { title: string; detail: string }> = {
  none: { title: "成為志工", detail: "送出報名後，由收容所管理員進行審核。" },
  pending: {
    title: "等待收容所審核",
    detail: "你的報名已送出，審核前不會取得照護資料。",
  },
  rejected: {
    title: "本次報名未通過",
    detail: "你可以查看說明，或在合適時再次報名。",
  },
  withdrawn: { title: "報名已撤回", detail: "需要時可以建立一筆新的報名。" },
  upcoming: { title: "授權即將開始", detail: "到開始時間後才能進入照護流程。" },
  active: {
    title: "志工授權使用中",
    detail: "你現在可以進入收容所的照護流程。",
  },
  expired: { title: "授權已到期", detail: "如要再次協助，請重新報名。" },
  revoked: { title: "授權已撤銷", detail: "如有疑問，請聯絡收容所管理員。" },
};

async function readStatus(response: Response): Promise<VolunteerStatus> {
  const body = await response.json();
  if (!response.ok) throw body;
  return body as VolunteerStatus;
}

export function VolunteerApplicationPage({
  idToken,
  shelterEntryReference,
  initialStatus = null,
}: Props) {
  const [status, setStatus] = useState<VolunteerStatus | null>(initialStatus);
  const [loading, setLoading] = useState(initialStatus === null);
  const [submitting, setSubmitting] = useState(false);
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialStatus !== null) return;
    if (!idToken || !shelterEntryReference) {
      setError("請從收容所提供的 LINE／LIFF 志工入口開啟此頁面。");
      setLoading(false);
      return;
    }
    let active = true;
    fetch("/v1/volunteer-applications/status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id_token: idToken,
        shelter_entry_reference: shelterEntryReference,
      }),
    })
      .then(readStatus)
      .then((value) => active && setStatus(value))
      .catch((reason) => active && setError(safeVolunteerError(reason?.code)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [idToken, initialStatus, shelterEntryReference]);

  async function submit() {
    if (submitting || !consent) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/v1/volunteer-applications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_token: idToken,
          shelter_entry_reference: shelterEntryReference,
          client_request_id: crypto.randomUUID(),
          consent_acknowledged: true,
        }),
      });
      setStatus(await readStatus(response));
    } catch (reason) {
      setError(safeVolunteerError((reason as { code?: string })?.code));
    } finally {
      setSubmitting(false);
    }
  }

  async function withdraw() {
    if (submitting || !status?.application) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(
        `/v1/volunteer-applications/${status.application.id}/withdraw`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id_token: idToken,
            shelter_entry_reference: shelterEntryReference,
            expected_version: status.application.version,
          }),
        },
      );
      setStatus(await readStatus(response));
    } catch (reason) {
      setError(safeVolunteerError((reason as { code?: string })?.code));
    } finally {
      setSubmitting(false);
    }
  }

  const effectiveStatus = status?.effective_status ?? "none";
  const copy = STATUS_COPY[effectiveStatus] ?? STATUS_COPY.none;
  const canApply = [
    "none",
    "rejected",
    "withdrawn",
    "expired",
    "revoked",
  ].includes(effectiveStatus);

  return (
    <main className="volunteer-application-page">
      <header className="volunteer-application-heading">
        <span className="eyebrow">
          {status?.organization.name ?? "StrayHub"}
        </span>
        <h1>志工報名</h1>
      </header>
      {loading ? (
        <p role="status" aria-live="polite">
          正在確認 LINE 身分與報名狀態…
        </p>
      ) : (
        <Card className="volunteer-application-card" aria-live="polite">
          <CardHeader>
            <CardTitle>{copy.title}</CardTitle>
            <p>{copy.detail}</p>
          </CardHeader>
          <CardContent className="volunteer-application-content">
            {status?.application?.decision_reason ? (
              <Alert className="volunteer-application-reason">
                {status.application.decision_reason}
              </Alert>
            ) : null}
            {status?.grant ? (
              <dl className="volunteer-grant-summary">
                <div>
                  <dt>目前收容所</dt>
                  <dd>{status.organization.name}</dd>
                </div>
                <div>
                  <dt>授權期間（台灣時間）</dt>
                  <dd>
                    {formatTaiwanDateTime(status.grant.valid_from)} ～{" "}
                    {formatTaiwanDateTime(status.grant.expires_at)}
                  </dd>
                </div>
                {effectiveStatus === "active" ||
                effectiveStatus === "upcoming" ? (
                  <div>
                    <dt>距離到期</dt>
                    <dd>{formatRemainingDuration(status.grant.expires_at)}</dd>
                  </div>
                ) : null}
              </dl>
            ) : null}
            {canApply && status?.organization.applications_enabled !== false ? (
              <div className="volunteer-application-actions">
                <label className="volunteer-consent">
                  <Checkbox
                    checked={consent}
                    onChange={(event) => setConsent(event.target.checked)}
                  />
                  <span>我確認送出志工報名，並同意由此收容所審核。</span>
                </label>
                <Button
                  type="button"
                  disabled={!consent || submitting}
                  onClick={submit}
                >
                  {submitting
                    ? "送出中…"
                    : effectiveStatus === "none"
                      ? "立即報名"
                      : "再次報名"}
                </Button>
              </div>
            ) : null}
            {effectiveStatus === "pending" ? (
              <Button
                variant="secondary"
                type="button"
                disabled={submitting}
                onClick={withdraw}
              >
                撤回報名
              </Button>
            ) : null}
            {effectiveStatus === "active" ? (
              <a
                href="/animal-confirmation"
                className="ui-button ui-button-default volunteer-application-link"
              >
                進入照護流程
              </a>
            ) : null}
          </CardContent>
        </Card>
      )}
      {error ? (
        <Alert className="volunteer-application-error" role="alert">
          {error}
        </Alert>
      ) : null}
    </main>
  );
}
