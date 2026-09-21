"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import {
  AccessGrantTable,
  type AccessGrant,
} from "../../../../features/volunteer-access/AccessGrantTable";
import { authFetch, type CurrentUser } from "../../../../lib/auth";
import { Button } from "../../../../components/ui/button";
import { Field } from "../../../../components/ui/field";
import { Input } from "../../../../components/ui/input";
import {
  ErrorState,
  LoadingState,
} from "../../../../components/management/StateViews";

export default function VolunteerAccessPage() {
  const [organizationId, setOrganizationId] = useState("");
  const [grants, setGrants] = useState<AccessGrant[]>([]);
  const [error, setError] = useState("");
  const [checkingRole, setCheckingRole] = useState(true);
  const [roleCheckError, setRoleCheckError] = useState("");
  const [requiresSupportReason, setRequiresSupportReason] = useState(false);
  const [supportReason, setSupportReason] = useState("");
  const [supportReasonReady, setSupportReasonReady] = useState(false);
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

  function supportHeaders(extra?: HeadersInit): Headers {
    const headers = new Headers(extra);
    if (requiresSupportReason) {
      headers.set(
        "X-Platform-Support-Reason",
        encodeURIComponent(supportReason.trim()),
      );
    }
    return headers;
  }

  async function load(id: string, userId: string) {
    const query = new URLSearchParams({ limit: "200" });
    if (userId) query.set("user_id", userId);
    const response = await authFetch(
      `/v1/organizations/${id}/volunteer-access-grants?${query.toString()}`,
      { headers: supportHeaders() },
    );
    if (!response.ok) throw new Error("無法載入志工授權");
    setGrants(((await response.json()) as { items: AccessGrant[] }).items);
  }

  useEffect(() => {
    const id = window.sessionStorage.getItem("active_organization_id") ?? "";
    setOrganizationId(id);
    if (!id) {
      setCheckingRole(false);
      return;
    }
    void (async () => {
      try {
        const profileResponse = await authFetch("/v1/auth/me");
        if (!profileResponse.ok) throw new Error("無法確認目前使用者權限");
        const profile = (await profileResponse.json()) as CurrentUser;
        if (profile.user.platform_role === "PLATFORM_ADMIN") {
          setRequiresSupportReason(true);
        } else {
          setSupportReasonReady(true);
        }
      } catch (roleError) {
        setRoleCheckError(
          roleError instanceof Error
            ? roleError.message
            : "無法確認目前使用者權限",
        );
      } finally {
        setCheckingRole(false);
      }
    })();
    // Role check runs once for the active shelter snapshot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!supportReasonReady || !organizationId) return;
    void load(organizationId, focusUserId).catch((reason) =>
      setError(reason instanceof Error ? reason.message : "載入失敗"),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [supportReasonReady, organizationId, focusUserId]);

  function submitSupportReason(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const reason = String(
      new FormData(event.currentTarget).get("platform-support-reason") ?? "",
    ).trim();
    if (!reason) {
      setError("請填寫平台支援原因");
      return;
    }
    setError("");
    setSupportReason(reason);
    setSupportReasonReady(true);
  }

  async function mutate(grantId: string, payload: object) {
    const response = await authFetch(
      `/v1/organizations/${organizationId}/volunteer-access-grants/${grantId}`,
      {
        method: "PATCH",
        headers: supportHeaders({ "Content-Type": "application/json" }),
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
      {checkingRole ? (
        <LoadingState
          title="正在確認使用者權限…"
          description="正在確認目前帳號是否為平台管理員。"
        />
      ) : roleCheckError ? (
        <ErrorState
          title="無法確認目前使用者權限"
          description={roleCheckError}
          action={
            <Button
              variant="secondary"
              type="button"
              onClick={() => window.location.reload()}
            >
              重試
            </Button>
          }
        />
      ) : requiresSupportReason && !supportReasonReady ? (
        <form className="ui-card ui-card-padded" onSubmit={submitSupportReason}>
          <Field>
            <label htmlFor="platform-support-reason">平台支援原因</label>
            <Input
              id="platform-support-reason"
              name="platform-support-reason"
              maxLength={500}
            />
          </Field>
          <p className="policy-note">
            平台管理員跨收容所查詢與調整志工授權都會記錄此原因。
          </p>
          {error ? <p role="alert">{error}</p> : null}
          <Button type="submit" variant="secondary">
            載入志工授權
          </Button>
        </form>
      ) : (
        <>
          {error ? <p role="alert">{error}</p> : null}
          {focusUserId ? (
            <p className="volunteer-access-focus">
              只顯示指定志工的授權紀錄（{visibleGrants.length} 筆）
              <Link href="/volunteers/access">顯示全部</Link>
            </p>
          ) : null}
          <AccessGrantTable grants={visibleGrants} onMutate={mutate} />
        </>
      )}
    </div>
  );
}
