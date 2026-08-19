"use client";

import { useEffect, useState } from "react";

import { authFetch } from "../../../../lib/auth";
import {
  VolunteerAccessPolicyForm,
  type VolunteerAccessPolicy,
} from "../../../../features/volunteer-access/VolunteerAccessPolicyForm";

export default function VolunteerAccessSettingsPage() {
  const [policy, setPolicy] = useState<VolunteerAccessPolicy | null>(null);

  useEffect(() => {
    const organizationId = window.sessionStorage.getItem(
      "active_organization_id",
    );
    if (!organizationId) return;
    void authFetch(
      `/v1/organizations/${organizationId}/volunteer-access-policy`,
    )
      .then((response) => response.json())
      .then(setPolicy);
  }, []);

  async function save(value: VolunteerAccessPolicy) {
    const response = await authFetch(
      `/v1/organizations/${value.organization_id}/volunteer-access-policy`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_version: value.version,
          applications_enabled: value.applications_enabled,
          default_grant_duration_hours: value.default_grant_duration_hours,
        }),
      },
    );
    if (!response.ok) throw new Error("志工設定儲存失敗，請重新載入");
    setPolicy((await response.json()) as VolunteerAccessPolicy);
  }

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">VOLUNTEER ACCESS</span>
          <h1>志工申請與授權設定</h1>
          <p>控制新申請入口，以及後續核准使用的預設有限期限。</p>
        </div>
      </div>
      {policy ? (
        <VolunteerAccessPolicyForm policy={policy} onSave={save} />
      ) : (
        <p>正在載入設定…</p>
      )}
    </div>
  );
}
