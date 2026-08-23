"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { authFetch, type CurrentUser } from "../../../../lib/auth";
import { Button } from "../../../../components/ui/button";
import { Field } from "../../../../components/ui/field";
import { Input } from "../../../../components/ui/input";
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
  const [requiresSupportReason, setRequiresSupportReason] = useState(false);
  const [supportReason, setSupportReason] = useState("");

  async function fetchPolicy(reason?: string) {
    const organizationId = window.sessionStorage.getItem(
      "active_organization_id",
    );
    if (!organizationId) throw new Error("請先選擇目前收容所");
    const headers = new Headers();
    if (reason) {
      headers.set("X-Platform-Support-Reason", encodeURIComponent(reason));
    }
    const response = await authFetch(
      `/v1/organizations/${organizationId}/volunteer-access-policy`,
      { headers },
    );
    if (!response.ok) throw new Error("無法載入志工授權設定");
    setPolicy((await response.json()) as VolunteerAccessPolicy);
  }

  async function initialize() {
    setLoading(true);
    setError("");
    try {
      const profileResponse = await authFetch("/v1/auth/me");
      if (!profileResponse.ok) throw new Error("無法確認目前使用者權限");
      const profile = (await profileResponse.json()) as CurrentUser;
      if (profile.user.platform_role === "PLATFORM_ADMIN") {
        setRequiresSupportReason(true);
        return;
      }
      await fetchPolicy();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "無法載入志工授權設定",
      );
    } finally {
      setLoading(false);
    }
  }

  async function loadWithSupportReason(reasonValue = supportReason) {
    const reason = reasonValue.trim();
    if (!reason) {
      setError("請填寫平台支援原因");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await fetchPolicy(reason);
    } catch (loadError) {
      setError(
        loadError instanceof Error ? loadError.message : "無法載入志工授權設定",
      );
    } finally {
      setLoading(false);
    }
  }

  function submitSupportReason(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const reason = String(
      new FormData(event.currentTarget).get("platform-support-reason") ?? "",
    );
    setSupportReason(reason);
    void loadWithSupportReason(reason);
  }

  useEffect(() => {
    void initialize();
    // Initial load runs once for the active shelter snapshot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save(value: VolunteerAccessPolicy) {
    const reason = supportReason.trim();
    if (requiresSupportReason && !reason) {
      throw new Error("請填寫平台支援原因");
    }
    const headers = new Headers({ "Content-Type": "application/json" });
    if (requiresSupportReason) {
      headers.set("X-Platform-Support-Reason", encodeURIComponent(reason));
    }
    const response = await authFetch(
      `/v1/organizations/${value.organization_id}/volunteer-access-policy`,
      {
        method: "PATCH",
        headers,
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
      {requiresSupportReason ? (
        <form className="ui-card ui-card-padded" onSubmit={submitSupportReason}>
          <Field>
            <label htmlFor="platform-support-reason">平台支援原因</label>
            <Input
              id="platform-support-reason"
              name="platform-support-reason"
              value={supportReason}
              disabled={loading}
              maxLength={500}
              onChange={(event) => setSupportReason(event.target.value)}
            />
          </Field>
          <p className="policy-note">
            平台管理員跨收容所查詢與修改都會記錄此原因。
          </p>
          <Button type="submit" variant="secondary" disabled={loading}>
            {loading ? "載入中…" : "載入設定"}
          </Button>
        </form>
      ) : null}
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
              onClick={() =>
                void (requiresSupportReason
                  ? loadWithSupportReason()
                  : initialize())
              }
            >
              重試
            </Button>
          }
        />
      ) : policy ? (
        <VolunteerAccessPolicyForm policy={policy} onSave={save} />
      ) : requiresSupportReason ? (
        <p role="status" className="policy-note">
          請先填寫平台支援原因，再載入目前收容所的設定。
        </p>
      ) : (
        <ErrorState
          title="找不到志工授權設定"
          description="請重新載入後再試。"
        />
      )}
    </div>
  );
}
