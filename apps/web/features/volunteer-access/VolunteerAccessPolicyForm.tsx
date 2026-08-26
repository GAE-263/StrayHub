"use client";

import React, { useState } from "react";
import { Alert } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Checkbox } from "../../components/ui/checkbox";
import { Field } from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { Toast } from "../../components/ui/toast";

export type VolunteerAccessPolicy = {
  organization_id: string;
  applications_enabled: boolean;
  default_grant_duration_hours: number;
  daily_application_limit: number;
  version: number;
};

export function VolunteerAccessPolicyForm({
  policy,
  onSave,
}: {
  policy: VolunteerAccessPolicy;
  onSave?: (value: VolunteerAccessPolicy) => Promise<void> | void;
}) {
  const [enabled, setEnabled] = useState(policy.applications_enabled);
  const [duration, setDuration] = useState(policy.default_grant_duration_hours);
  const [dailyLimit, setDailyLimit] = useState(policy.daily_application_limit);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (duration <= 0) {
      setError("預設授權期限必須大於 0 小時");
      return;
    }
    if (dailyLimit <= 0) {
      setError("每日報名人數上限必須大於 0");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onSave?.({
        ...policy,
        applications_enabled: enabled,
        default_grant_duration_hours: duration,
        daily_application_limit: dailyLimit,
      });
      setToast("設定已儲存，只影響後續建立的授權。");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "志工設定儲存失敗，請重試",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="ui-card ui-card-padded policy-form">
      <label className="policy-checkbox">
        <Checkbox
          checked={enabled}
          disabled={busy}
          onChange={(event) => setEnabled(event.target.checked)}
        />
        開放志工新申請
      </label>
      <Field>
        <label htmlFor="policy-duration">預設授權期限（小時）</label>
        <Input
          id="policy-duration"
          type="number"
          min={1}
          value={duration}
          disabled={busy}
          onChange={(event) => setDuration(Number(event.target.value))}
        />
      </Field>
      <Field>
        <label htmlFor="policy-daily-limit">每日報名人數上限</label>
        <Input
          id="policy-daily-limit"
          type="number"
          min={1}
          value={dailyLimit}
          disabled={busy}
          onChange={(event) => setDailyLimit(Number(event.target.value))}
        />
      </Field>
      <p className="policy-note">
        變更只影響後續建立的授權，不追溯既有批次或授權。
      </p>
      <Button type="submit" disabled={busy}>
        {busy ? "儲存中…" : "儲存設定"}
      </Button>
      {error ? <Alert role="alert">{error}</Alert> : null}
      {toast ? <Toast onClose={() => setToast("")}>{toast}</Toast> : null}
    </form>
  );
}
