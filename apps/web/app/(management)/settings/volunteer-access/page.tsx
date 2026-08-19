"use client";

import { useEffect, useState } from "react";

import { authFetch } from "../../../../lib/auth";
import { Button } from "../../../../components/ui/button";
import {
  ErrorState,
  LoadingState,
} from "../../../../components/management/StateViews";
import {
  VolunteerAccessPolicyForm,
  type VolunteerAccessPolicy,
} from "../../../../features/volunteer-access/VolunteerAccessPolicyForm";

export default function VolunteerAccessSettingsPage() {
  const [policy, setPolicy] = useState<VolunteerAccessPolicy | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const organizationId = window.sessionStorage.getItem(
        "active_organization_id",
      );
      if (!organizationId) throw new Error("請先選擇目前收容所");
      const response = await authFetch(
        `/v1/organizations/${organizationId}/volunteer-access-policy`,
      );
      if (!response.ok) throw new Error("無法載入志工授權設定");
      setPolicy((await response.json()) as VolunteerAccessPolicy);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "無法載入志工授權設定",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // Initial load runs once for the active shelter snapshot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      {loading ? (
        <LoadingState
          title="正在載入志工授權設定…"
          description="正在取得目前收容所的申請與期限政策。"
        />
      ) : error ? (
        <ErrorState
          title="無法載入志工授權設定"
          description={error}
          action={
            <Button
              variant="secondary"
              type="button"
              onClick={() => void load()}
            >
              重試
            </Button>
          }
        />
      ) : policy ? (
        <VolunteerAccessPolicyForm policy={policy} onSave={save} />
      ) : (
        <ErrorState
          title="找不到志工授權設定"
          description="請重新載入後再試。"
        />
      )}
    </div>
  );
}
