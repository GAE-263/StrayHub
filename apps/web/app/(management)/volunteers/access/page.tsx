"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  AccessGrantTable,
  type AccessGrant,
} from "../../../../features/volunteer-access/AccessGrantTable";
import { authFetch } from "../../../../lib/auth";

export default function VolunteerAccessPage() {
  const [organizationId, setOrganizationId] = useState("");
  const [grants, setGrants] = useState<AccessGrant[]>([]);
  const [error, setError] = useState("");
  const searchParams = useSearchParams();
  // Care history links here to follow one volunteer; without the filter the
  // whole org's grants would be dumped on the reader.
  const focusUserId = searchParams.get("user_id") ?? "";
  const visibleGrants = useMemo(
    () =>
      focusUserId
        ? grants.filter((grant) => grant.user_id === focusUserId)
        : grants,
    [grants, focusUserId],
  );

  async function load(id: string, userId: string) {
    const query = new URLSearchParams({ limit: "200" });
    if (userId) query.set("user_id", userId);
    const response = await authFetch(
      `/v1/organizations/${id}/volunteer-access-grants?${query.toString()}`,
    );
    if (!response.ok) throw new Error("無法載入志工授權");
    setGrants(((await response.json()) as { items: AccessGrant[] }).items);
  }

  useEffect(() => {
    const id = window.sessionStorage.getItem("active_organization_id") ?? "";
    setOrganizationId(id);
    if (id)
      void load(id, focusUserId).catch((reason) => setError(reason.message));
  }, [focusUserId]);

  async function mutate(grantId: string, payload: object) {
    const response = await authFetch(
      `/v1/organizations/${organizationId}/volunteer-access-grants/${grantId}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
    if (response.status === 409) {
      throw new Error("授權已由其他管理員更新，輸入已保留，請重新載入後確認");
    }
    if (!response.ok) throw new Error("授權更新失敗，請確認期限與原因");
    const updated = (await response.json()) as AccessGrant;
    setGrants((current) =>
      current.map((grant) => (grant.id === updated.id ? updated : grant)),
    );
    return updated;
  }

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">VOLUNTEER ACCESS</span>
          <h1>志工授權管理</h1>
          <p>調整有限期限、立即失效或撤銷；歷史週期與原始照護資料會保留。</p>
        </div>
      </div>
      {error ? <p role="alert">{error}</p> : null}
      {focusUserId ? (
        <p className="volunteer-access-focus">
          只顯示指定志工的授權紀錄（{visibleGrants.length} 筆）
          <Link href="/volunteers/access">顯示全部</Link>
        </p>
      ) : null}
      <AccessGrantTable grants={visibleGrants} onMutate={mutate} />
    </div>
  );
}
