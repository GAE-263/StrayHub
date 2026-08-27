"use client";

import React from "react";
import { useEffect, useMemo, useState } from "react";
import { Alert } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { Checkbox } from "../../components/ui/checkbox";
import { Dialog } from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { Toast } from "../../components/ui/toast";

import {
  formatRemainingDuration,
  formatTaiwanDateTime,
  safeVolunteerError,
  type VolunteerStatus,
} from "./volunteerAccess";

type SharedProps = {
  idToken: string;
  initialStatus?: VolunteerStatus | null;
};

type Props = SharedProps &
  (
    | { organizationId: string; shelterEntryReference?: never }
    | { organizationId?: never; shelterEntryReference: string }
  );

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

function formatLocalDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatServiceDate(value: string): string {
  return new Intl.DateTimeFormat("zh-TW", {
    month: "numeric",
    day: "numeric",
    weekday: "short",
  }).format(new Date(`${value}T12:00:00`));
}

function formatServiceDateParts(value: string): {
  date: string;
  weekday: string;
} {
  const date = new Date(`${value}T12:00:00`);
  return {
    date: new Intl.DateTimeFormat("zh-TW", {
      month: "numeric",
      day: "numeric",
    }).format(date),
    weekday: new Intl.DateTimeFormat("zh-TW", { weekday: "short" }).format(
      date,
    ),
  };
}

export function VolunteerApplicationPage(props: Props) {
  const { idToken, initialStatus = null } = props;
  const organizationId = props.organizationId;
  const shelterEntryReference = props.shelterEntryReference;
  const targetPayload = useMemo(
    () =>
      organizationId
        ? { organization_id: organizationId }
        : { shelter_entry_reference: shelterEntryReference },
    [organizationId, shelterEntryReference],
  );
  const targetKey = organizationId
    ? `organization:${organizationId}`
    : `entry:${shelterEntryReference}`;
  const [status, setStatus] = useState<VolunteerStatus | null>(initialStatus);
  const [loading, setLoading] = useState(initialStatus === null);
  const [submitting, setSubmitting] = useState(false);
  const [applicantName, setApplicantName] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [insuranceIdentity, setInsuranceIdentity] = useState("");
  const [consent, setConsent] = useState(false);
  const [insuranceConsent, setInsuranceConsent] = useState(false);
  const [selectedServiceDates, setSelectedServiceDates] = useState<string[]>(
    [],
  );
  const [error, setError] = useState<string | null>(null);
  const [withdrawOpen, setWithdrawOpen] = useState(false);
  const [toast, setToast] = useState("");
  const serviceDateOptions = useMemo(() => {
    const options: string[] = [];
    const today = new Date();
    today.setHours(12, 0, 0, 0);
    for (let offset = 0; offset < 14; offset += 1) {
      const value = new Date(today);
      value.setDate(today.getDate() + offset);
      options.push(formatLocalDate(value));
    }
    return options;
  }, []);

  useEffect(() => {
    let active = true;
    setStatus(initialStatus);
    setLoading(initialStatus === null);
    setError(null);
    setApplicantName("");
    setPhoneNumber("");
    setInsuranceIdentity("");
    setConsent(false);
    setInsuranceConsent(false);
    setSelectedServiceDates([]);
    setWithdrawOpen(false);
    setToast("");
    if (initialStatus !== null) {
      return () => {
        active = false;
      };
    }
    if (!idToken || (!organizationId && !shelterEntryReference)) {
      setError("請從收容所提供的 LINE／LIFF 志工入口開啟此頁面。");
      setLoading(false);
      return () => {
        active = false;
      };
    }
    fetch("/v1/volunteer-applications/status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id_token: idToken,
        ...targetPayload,
      }),
    })
      .then(readStatus)
      .then((value) => active && setStatus(value))
      .catch((reason) => active && setError(safeVolunteerError(reason?.code)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [
    idToken,
    initialStatus,
    organizationId,
    shelterEntryReference,
    targetKey,
    targetPayload,
  ]);

  async function submit() {
    const insuranceRequired = status?.organization.insurance_required === true;
    if (
      submitting ||
      !consent ||
      !applicantName.trim() ||
      !phoneNumber.trim() ||
      selectedServiceDates.length === 0 ||
      (insuranceRequired && (!insuranceIdentity.trim() || !insuranceConsent))
    )
      return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/v1/volunteer-applications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_token: idToken,
          ...targetPayload,
          applicant_name: applicantName.trim(),
          phone_number: phoneNumber.trim(),
          ...(insuranceRequired
            ? {
                insurance_identity: insuranceIdentity.trim(),
                insurance_consent_acknowledged: true,
              }
            : {}),
          client_request_id: crypto.randomUUID(),
          consent_acknowledged: true,
          service_dates: selectedServiceDates,
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
            ...targetPayload,
            expected_version: status.application.version,
          }),
        },
      );
      const nextStatus = await readStatus(response);
      setStatus(nextStatus);
      setWithdrawOpen(false);
      setToast("志工報名已撤回");
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
  const insuranceRequired = status?.organization.insurance_required === true;
  const submitDisabled =
    !consent ||
    !applicantName.trim() ||
    !phoneNumber.trim() ||
    selectedServiceDates.length === 0 ||
    (insuranceRequired && (!insuranceIdentity.trim() || !insuranceConsent)) ||
    submitting;

  return (
    <main className="volunteer-application-page">
      <header className="volunteer-application-heading">
        <span className="eyebrow">申請成為</span>
        <h1>{status?.organization.name ?? "志工報名"}</h1>
        <p>志工</p>
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
            {status?.organization.applications_enabled === false &&
            effectiveStatus !== "pending" ? (
              <Alert>此收容所目前暫停接受新申請。</Alert>
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
                <div className="volunteer-application-fields">
                  <label htmlFor="applicant-name">
                    姓名
                    <Input
                      id="applicant-name"
                      type="text"
                      autoComplete="name"
                      placeholder="請輸入姓名"
                      value={applicantName}
                      onChange={(event) => setApplicantName(event.target.value)}
                      required
                    />
                  </label>
                  <label htmlFor="phone-number">
                    手機號碼
                    <Input
                      id="phone-number"
                      type="tel"
                      autoComplete="tel"
                      inputMode="tel"
                      placeholder="例如 0912 345 678"
                      value={phoneNumber}
                      onChange={(event) => setPhoneNumber(event.target.value)}
                      required
                    />
                  </label>
                  {insuranceRequired ? (
                    <>
                      <label htmlFor="insurance-identity">
                        保險身分資料
                        <Input
                          id="insurance-identity"
                          type="text"
                          placeholder="請輸入保險所需資料"
                          value={insuranceIdentity}
                          onChange={(event) =>
                            setInsuranceIdentity(event.target.value)
                          }
                          required
                        />
                      </label>
                      <label className="volunteer-consent">
                        <Checkbox
                          checked={insuranceConsent}
                          onChange={(event) =>
                            setInsuranceConsent(event.target.checked)
                          }
                        />
                        <span>我同意此資料僅供保險資格確認使用。</span>
                      </label>
                    </>
                  ) : null}
                </div>
                <label className="volunteer-consent">
                  <Checkbox
                    checked={consent}
                    onChange={(event) => setConsent(event.target.checked)}
                  />
                  <span>我確認送出志工報名，並同意由此收容所審核。</span>
                </label>
                <fieldset
                  className="volunteer-service-date-picker"
                  aria-describedby="service-date-hint"
                >
                  <legend>選擇服務日期</legend>
                  <p id="service-date-hint">可複選，限今天起兩週內</p>
                  <div className="volunteer-service-date-grid">
                    {serviceDateOptions.map((serviceDate) => {
                      const selected =
                        selectedServiceDates.includes(serviceDate);
                      const parts = formatServiceDateParts(serviceDate);
                      return (
                        <label
                          key={serviceDate}
                          className="volunteer-service-date-option"
                          data-selected={selected}
                        >
                          <Checkbox
                            className="volunteer-service-date-checkbox"
                            aria-label={`服務日期 ${formatServiceDate(serviceDate)}`}
                            checked={selected}
                            onChange={(event) =>
                              setSelectedServiceDates((current) =>
                                event.target.checked
                                  ? [...current, serviceDate]
                                  : current.filter(
                                      (value) => value !== serviceDate,
                                    ),
                              )
                            }
                          />
                          <span className="volunteer-service-date-weekday">
                            {parts.weekday}
                          </span>
                          <span className="volunteer-service-date-value">
                            {parts.date}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                </fieldset>
                <Button
                  type="button"
                  disabled={submitDisabled}
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
                onClick={() => setWithdrawOpen(true)}
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
      <Dialog
        open={withdrawOpen}
        title="確認撤回志工報名"
        role="alertdialog"
        closeLabel="關閉撤回確認"
        onClose={() => {
          if (!submitting) setWithdrawOpen(false);
        }}
      >
        <p>撤回後本次申請將停止審核；需要協助時仍可重新報名。</p>
        <div className="ui-dialog-actions">
          <Button
            variant="secondary"
            type="button"
            disabled={submitting}
            onClick={() => setWithdrawOpen(false)}
          >
            保留報名
          </Button>
          <Button
            variant="destructive"
            type="button"
            disabled={submitting}
            onClick={() => void withdraw()}
          >
            {submitting ? "撤回中…" : "確認撤回"}
          </Button>
        </div>
      </Dialog>
      {toast && (
        <Toast messageKey={toast} onClose={() => setToast("")}>
          {toast}
        </Toast>
      )}
    </main>
  );
}
