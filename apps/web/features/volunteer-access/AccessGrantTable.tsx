"use client";

import React from "react";
import { useState } from "react";

import { formatTaiwanDateTime } from "./volunteerAccess";
import { MembershipPermissionDialog } from "../../components/management/MembershipPermissionDialog";
import { Toast } from "../../components/ui/toast";

export type AccessGrant = {
  id: string;
  display_name: string;
  status: string;
  valid_from: string;
  expires_at: string;
  version: number;
  source_type: string;
  revocation_reason?: string | null;
};

type PendingGrantChange = {
  grant: AccessGrant;
  action: "update_period" | "revoke";
  payload: object;
  before: string;
  after: string;
  authorizationImpact?: string;
};

function localDateTime(value: string) {
  const date = new Date(value);
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return shifted.toISOString().slice(0, 16);
}

export function AccessGrantTable({
  grants,
  onMutate,
}: {
  grants: AccessGrant[];
  onMutate: (grantId: string, payload: object) => Promise<AccessGrant>;
}) {
  const [status, setStatus] = useState("all");
  const [drafts, setDrafts] = useState<
    Record<string, { from: string; to: string; reason: string }>
  >({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [pending, setPending] = useState<PendingGrantChange | null>(null);
  const [confirming, setConfirming] = useState(false);
  const visible = grants.filter(
    (grant) => status === "all" || grant.status === status,
  );

  function draft(grant: AccessGrant) {
    return (
      drafts[grant.id] ?? {
        from: localDateTime(grant.valid_from),
        to: localDateTime(grant.expires_at),
        reason: "",
      }
    );
  }

  function updateDraft(
    grant: AccessGrant,
    values: Partial<ReturnType<typeof draft>>,
  ) {
    setDrafts((current) => ({
      ...current,
      [grant.id]: { ...draft(grant), ...values },
    }));
  }

  async function mutate(
    grant: AccessGrant,
    action: "update_period" | "revoke",
  ) {
    const values = draft(grant);
    if (action === "revoke" && !values.reason.trim()) {
      setMessage("撤銷必須填寫原因");
      return;
    }
    const expiresAt = new Date(values.to);
    const immediate =
      action === "update_period" && expiresAt.getTime() <= Date.now();
    const payload =
      action === "revoke"
        ? {
            action,
            expected_version: grant.version,
            reason: values.reason.trim(),
          }
        : {
            action,
            expected_version: grant.version,
            valid_from: new Date(values.from).toISOString(),
            expires_at: expiresAt.toISOString(),
            confirm_immediate_expiry: immediate,
            reason: values.reason.trim() || null,
          };
    setPending({
      grant,
      action,
      payload,
      before:
        action === "revoke"
          ? `有效授權／版本 ${grant.version}`
          : `${formatTaiwanDateTime(grant.valid_from)} ～ ${formatTaiwanDateTime(grant.expires_at)}`,
      after:
        action === "revoke"
          ? "已撤銷"
          : `${values.from || "現在"} ～ ${values.to || "新期限"}`,
      authorizationImpact: immediate
        ? "新期限已到期，這次操作會立即失效。"
        : undefined,
    });
  }

  async function confirmMutation() {
    if (!pending) return;
    setConfirming(true);
    setError("");
    try {
      await onMutate(pending.grant.id, pending.payload);
      setPending(null);
      setToast(
        pending.action === "revoke"
          ? `已撤銷「${pending.grant.display_name}」的志工授權`
          : `已更新「${pending.grant.display_name}」的志工授權期限`,
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "授權已由其他管理員更新，請重新載入後確認",
      );
    } finally {
      setConfirming(false);
    }
  }

  return (
    <section className="panel ui-card" aria-labelledby="grant-title">
      <h2 id="grant-title">志工授權與歷史週期</h2>
      <label>
        狀態篩選
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
        >
          <option value="all">全部</option>
          <option value="active">有效／即將開始</option>
          <option value="expired">已到期</option>
          <option value="revoked">已撤銷</option>
        </select>
      </label>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th>志工</th>
              <th>狀態與來源</th>
              <th>期間（台灣時間）</th>
              <th>管理</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((grant) => {
              const values = draft(grant);
              return (
                <tr key={grant.id}>
                  <td>{grant.display_name}</td>
                  <td>
                    {grant.status}／{grant.source_type}
                    {grant.revocation_reason ? (
                      <p>{grant.revocation_reason}</p>
                    ) : null}
                  </td>
                  <td>
                    {formatTaiwanDateTime(grant.valid_from)} ～{" "}
                    {formatTaiwanDateTime(grant.expires_at)}
                  </td>
                  <td>
                    {grant.status === "active" ? (
                      <div className="grid gap-2">
                        <label>
                          開始
                          <input
                            aria-label={`${grant.display_name} 開始時間`}
                            type="datetime-local"
                            value={values.from}
                            onChange={(event) =>
                              updateDraft(grant, { from: event.target.value })
                            }
                          />
                        </label>
                        <label>
                          到期
                          <input
                            aria-label={`${grant.display_name} 到期時間`}
                            type="datetime-local"
                            value={values.to}
                            onChange={(event) =>
                              updateDraft(grant, { to: event.target.value })
                            }
                          />
                        </label>
                        <label>
                          原因
                          <input
                            aria-label={`${grant.display_name} 操作原因`}
                            value={values.reason}
                            onChange={(event) =>
                              updateDraft(grant, { reason: event.target.value })
                            }
                          />
                        </label>
                        <button
                          type="button"
                          onClick={() => mutate(grant, "update_period")}
                        >
                          更新期限
                        </button>
                        <button
                          type="button"
                          onClick={() => mutate(grant, "revoke")}
                        >
                          撤銷授權
                        </button>
                      </div>
                    ) : (
                      <span>歷史週期（不可修改）</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {error ? <p role="alert">{error}</p> : null}
      {message ? (
        <p role="status" aria-live="polite">
          {message}
        </p>
      ) : null}
      {toast ? <Toast>{toast}</Toast> : null}
      <MembershipPermissionDialog
        open={Boolean(pending)}
        identity={pending?.grant.display_name ?? "志工"}
        operation={
          pending?.action === "revoke" ? "撤銷志工授權" : "調整志工授權期限"
        }
        before={pending?.before ?? ""}
        after={pending?.after ?? ""}
        authorizationImpact={pending?.authorizationImpact}
        onClose={() => setPending(null)}
        onConfirm={() => void confirmMutation()}
        confirming={confirming}
      />
    </section>
  );
}
