"use client";

import React, { useState } from "react";

export type VolunteerAccessPolicy = {
  organization_id: string;
  applications_enabled: boolean;
  default_grant_duration_hours: number;
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
  const [message, setMessage] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (duration <= 0) {
      setMessage("預設授權期限必須大於 0 小時");
      return;
    }
    await onSave?.({
      ...policy,
      applications_enabled: enabled,
      default_grant_duration_hours: duration,
    });
    setMessage("設定已儲存，只影響後續建立的授權。");
  }

  return (
    <form onSubmit={submit} className="panel ui-card space-y-5">
      <label className="flex gap-3">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(event) => setEnabled(event.target.checked)}
        />
        開放志工新申請
      </label>
      <label className="block">
        預設授權期限（小時）
        <input
          className="mt-2 block min-h-11 rounded-lg border px-3"
          type="number"
          min={1}
          value={duration}
          onChange={(event) => setDuration(Number(event.target.value))}
        />
      </label>
      <p className="text-sm text-slate-600">
        變更只影響後續建立的授權，不追溯既有批次或授權。
      </p>
      <button
        type="submit"
        className="min-h-11 rounded-lg bg-emerald-700 px-5 text-white"
      >
        儲存設定
      </button>
      <p role="status" aria-live="polite">
        {message}
      </p>
    </form>
  );
}
