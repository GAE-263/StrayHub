"use client";

import { useEffect, useState } from "react";

import {
  AccessGrantTable,
  type AccessGrant,
} from "../../../../features/volunteer-access/AccessGrantTable";
import { authFetch } from "../../../../lib/auth";

export default function VolunteerAccessPage() {
  const [organizationId, setOrganizationId] = useState("");
  const [grants, setGrants] = useState<AccessGrant[]>([]);
  const [error, setError] = useState("");

  async function load(id: string) {
    const response = await authFetch(
      `/v1/organizations/${id}/volunteer-access-grants?limit=200`,
    );
    if (!response.ok) throw new Error("無法載入志工授權");
    setGrants(((await response.json()) as { items: AccessGrant[] }).items);
  }

  useEffect(() => {
    const id = window.sessionStorage.getItem("active_organization_id") ?? "";
    setOrganizationId(id);
    if (id) void load(id).catch((reason) => setError(reason.message));
  }, []);

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
      <AccessGrantTable grants={grants} onMutate={mutate} />
    </div>
  );
}
