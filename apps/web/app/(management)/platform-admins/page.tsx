"use client";

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { authFetch, clearAuth, type CurrentUser } from "../../../lib/auth";
import {
  EmptyState,
  LoadingState,
} from "../../../components/management/StateViews";
import { Alert } from "../../../components/ui/alert";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../../components/ui/card";
import { Dialog } from "../../../components/ui/dialog";
import { Field } from "../../../components/ui/field";
import { Input } from "../../../components/ui/input";
import { Select } from "../../../components/ui/select";
import { Toast } from "../../../components/ui/toast";

type Policy = {
  min_active_admins: number;
  max_active_admins: number;
  active_count: number;
  available_slots: number;
};

type Admin = {
  user_id: string;
  username: string | null;
  display_name: string;
  user_status: "active" | "disabled";
  platform_role: "PLATFORM_ADMIN" | null;
  effective_status: "active" | "disabled";
  can_enable: boolean;
  can_disable: boolean;
  can_demote: boolean;
};

type Candidate = {
  user_id: string;
  username: string | null;
  display_name: string;
};

type ListResponse = { policy: Policy; items: Admin[] };

type MutationResponse = {
  item: Admin;
  policy: Policy;
  operation_id: string;
};

type AuditRecord = {
  id: string;
  operation_id: string;
  action: string;
  result: "success" | "denied";
  reason: string | null;
  created_at: string;
};

type PendingMutation = {
  title: string;
  description: string;
  confirmLabel: string;
  action: () => Promise<void>;
};

async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = "操作失敗";
    try {
      message =
        ((await response.json()) as { message?: string }).message ?? message;
    } catch {
      // Keep a safe message for non-JSON responses.
    }
    throw new Error(`${response.status}: ${message}`);
  }
  return response.json() as Promise<T>;
}

export default function PlatformAdminsPage() {
  const router = useRouter();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [admins, setAdmins] = useState<Admin[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [auditRecords, setAuditRecords] = useState<AuditRecord[]>([]);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [replacementOpen, setReplacementOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [promoteUserId, setPromoteUserId] = useState("");
  const [outgoingUserId, setOutgoingUserId] = useState("");
  const [replacementUserId, setReplacementUserId] = useState("");
  const [reason, setReason] = useState("");
  const [pendingMutation, setPendingMutation] =
    useState<PendingMutation | null>(null);

  const request = useCallback(async <T,>(path: string, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    headers.set("Content-Type", "application/json");
    return readResponse<T>(await authFetch(path, { ...init, headers }));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [adminData, candidateData, profileData] = await Promise.all([
        request<ListResponse>("/v1/platform/administrators"),
        request<Candidate[]>("/v1/platform/administrators/candidates"),
        request<CurrentUser>("/v1/auth/me"),
      ]);
      const auditData = await request<AuditRecord[]>(
        "/v1/platform/administrators/audit?limit=20",
      );
      setPolicy(adminData.policy);
      setAdmins(adminData.items);
      setCandidates(candidateData);
      setCurrentUser(profileData);
      setAuditRecords(auditData);
      setOutgoingUserId(
        (current) =>
          current ||
          adminData.items.find((item) => item.effective_status === "active")
            ?.user_id ||
          "",
      );
    } finally {
      setLoading(false);
    }
  }, [request]);

  useEffect(() => {
    void load().catch((requestError: unknown) =>
      setError(
        requestError instanceof Error
          ? requestError.message
          : "無法載入平台管理員",
      ),
    );
  }, [load]);

  const activeAdmins = useMemo(
    () => admins.filter((admin) => admin.effective_status === "active"),
    [admins],
  );
  const disabledAdmins = useMemo(
    () => admins.filter((admin) => admin.effective_status !== "active"),
    [admins],
  );

  const run = async (action: () => Promise<void>) => {
    setError("");
    setMessage("");
    try {
      await action();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "操作失敗");
    }
  };

  const queueMutation = (mutation: PendingMutation) => {
    setPendingMutation(mutation);
  };

  const confirmPendingMutation = async () => {
    const mutation = pendingMutation;
    if (!mutation || submittingRef.current) return;
    submittingRef.current = true;
    setSubmitting(true);
    try {
      setPendingMutation(null);
      await mutation.action();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "操作失敗");
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  const mutate = async (path: string, body?: unknown) => {
    const result = await request<MutationResponse>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });

    const invalidatesCurrentSession =
      result.item.user_id === currentUser?.user.id &&
      (result.item.user_status !== "active" ||
        result.item.platform_role !== "PLATFORM_ADMIN");
    if (invalidatesCurrentSession) {
      clearAuth();
      router.replace("/login");
      return;
    }
    await load();
  };

  const createAdmin = async (event: FormEvent) => {
    event.preventDefault();
    queueMutation({
      title: "確認建立平台管理員帳號",
      description: `將建立並立即啟用「${displayName || username}」的平台管理員帳號，啟用中的管理員數量將變為 ${(policy?.active_count ?? 0) + 1}。`,
      confirmLabel: "確認建立",
      action: async () => {
        await mutate("/v1/platform/administrators", {
          username,
          display_name: displayName,
          temporary_password: temporaryPassword,
        });
        setUsername("");
        setDisplayName("");
        setTemporaryPassword("");
        setCreateOpen(false);
        setMessage("平台管理員帳號已建立。");
      },
    });
  };

  const promote = async (event: FormEvent) => {
    event.preventDefault();
    const candidate = candidates.find((item) => item.user_id === promoteUserId);
    queueMutation({
      title: "確認提升平台管理員權限",
      description: `將「${candidate?.display_name ?? promoteUserId}」加入平台管理員，啟用中的管理員數量將變為 ${(policy?.active_count ?? 0) + 1}。`,
      confirmLabel: "確認提升",
      action: async () => {
        await mutate(`/v1/platform/administrators/${promoteUserId}/promote`);
        setPromoteUserId("");
        setMessage("帳號已提升為平台管理員。");
      },
    });
  };

  const replace = async (event: FormEvent) => {
    event.preventDefault();
    const outgoing = activeAdmins.find(
      (item) => item.user_id === outgoingUserId,
    );
    const replacement = candidates.find(
      (item) => item.user_id === replacementUserId,
    );
    queueMutation({
      title: "確認替換平台管理員",
      description: `將「${outgoing?.display_name ?? outgoingUserId}」的管理權限交接給「${replacement?.display_name ?? replacementUserId}」，啟用中的管理員數量維持 ${policy?.active_count ?? 0}。原因：${reason}`,
      confirmLabel: "確認替換",
      action: async () => {
        await mutate("/v1/platform/administrators/replacements", {
          outgoing_user_id: outgoingUserId,
          replacement_user_id: replacementUserId,
          reason,
        });
        setReplacementOpen(false);
        setReplacementUserId("");
        setReason("");
        setMessage("平台管理員替換已完成。");
      },
    });
  };

  const renderAdmin = (admin: Admin) => (
    <li
      className={`platform-admin-item ${admin.effective_status === "active" ? "" : "is-disabled"}`}
      key={admin.user_id}
    >
      <div>
        <strong>{admin.display_name}</strong>
        <span className="platform-admin-username">
          帳號：{admin.username ?? "未設定"}
        </span>
      </div>
      <div className="platform-admin-meta">
        <Badge>
          {admin.effective_status === "active" ? "啟用中" : "已停用"}
        </Badge>
        <span className="platform-admin-actions">
          {admin.can_enable ? (
            <Button
              variant="secondary"
              type="button"
              onClick={() =>
                queueMutation({
                  title: "確認重新啟用平台管理員",
                  description: `將「${admin.display_name}」重新啟用，該帳號會恢復平台管理員權限。`,
                  confirmLabel: "確認重新啟用",
                  action: () =>
                    mutate(
                      `/v1/platform/administrators/${admin.user_id}/enable`,
                    ).then(() => setMessage("平台管理員已重新啟用。")),
                })
              }
            >
              重新啟用
            </Button>
          ) : null}
          {admin.can_disable ? (
            <Button
              variant="secondary"
              type="button"
              onClick={() =>
                queueMutation({
                  title: "確認停用平台管理員",
                  description: `將停用「${admin.display_name}」。${
                    admin.user_id === currentUser?.user.id
                      ? "這會立即使你目前的管理員 session 登出。"
                      : "該帳號將無法繼續執行平台管理操作。"
                  }`,
                  confirmLabel: "確認停用",
                  action: () =>
                    mutate(
                      `/v1/platform/administrators/${admin.user_id}/disable`,
                    ).then(() => setMessage("平台管理員已停用。")),
                })
              }
            >
              停用
            </Button>
          ) : null}
          {admin.can_demote ? (
            <Button
              variant="secondary"
              type="button"
              onClick={() =>
                queueMutation({
                  title: "確認降低平台管理員權限",
                  description: `將「${admin.display_name}」降為一般帳號，平台管理員權限會立即移除。`,
                  confirmLabel: "確認降權",
                  action: () =>
                    mutate(
                      `/v1/platform/administrators/${admin.user_id}/demote`,
                    ).then(() => setMessage("平台管理員權限已移除。")),
                })
              }
            >
              降權
            </Button>
          ) : null}
        </span>
      </div>
    </li>
  );

  return (
    <section
      className="platform-admin-page"
      aria-labelledby="platform-admin-title"
    >
      <div className="page-heading platform-admin-heading">
        <div>
          <span className="eyebrow">PLATFORM GOVERNANCE</span>
          <h1 id="platform-admin-title">平台管理員</h1>
          <p>管理平台層級帳號，不需要選擇收容所。</p>
        </div>
        <div className="platform-admin-header-actions">
          <Button
            type="button"
            onClick={() => setCreateOpen(true)}
            disabled={!policy || policy.available_slots === 0}
          >
            建立帳號
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => setReplacementOpen(true)}
            disabled={activeAdmins.length === 0 || candidates.length === 0}
          >
            替換管理員
          </Button>
        </div>
      </div>
      {error ? <Alert role="alert">操作失敗：{error}</Alert> : null}
      {message ? <Toast>{message}</Toast> : null}
      {loading ? <LoadingState title="正在載入平台管理員…" /> : null}
      {!loading && policy ? (
        <div className="platform-policy-grid" aria-label="平台管理員政策摘要">
          <Card>
            <CardContent>
              <span className="eyebrow">啟用中</span>
              <strong className="platform-policy-number">
                {policy.active_count}
              </strong>
              <span>位平台管理員</span>
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <span className="eyebrow">治理範圍</span>
              <strong className="platform-policy-number">
                {policy.min_active_admins}–{policy.max_active_admins}
              </strong>
              <span>正常人數</span>
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <span className="eyebrow">剩餘名額</span>
              <strong className="platform-policy-number">
                {policy.available_slots}
              </strong>
              <span>位</span>
            </CardContent>
          </Card>
        </div>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle>啟用中的平台管理員</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <LoadingState title="正在載入啟用中的平台管理員…" />
          ) : activeAdmins.length ? (
            <ul className="platform-admin-list">
              {activeAdmins.map(renderAdmin)}
            </ul>
          ) : (
            <EmptyState title="目前沒有啟用中的平台管理員" />
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>平台異動紀錄</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <LoadingState title="正在載入平台異動紀錄…" />
          ) : auditRecords.length ? (
            <ul className="platform-audit-list">
              {auditRecords.map((record) => (
                <li key={record.id}>
                  <strong>{record.action}</strong>
                  <Badge>{record.result === "success" ? "成功" : "拒絕"}</Badge>
                  <span>{record.reason ?? "平台管理員異動"}</span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="目前沒有平台管理員異動紀錄" />
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>已停用的平台管理員</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <LoadingState title="正在載入已停用的平台管理員…" />
          ) : disabledAdmins.length ? (
            <ul className="platform-admin-list">
              {disabledAdmins.map(renderAdmin)}
            </ul>
          ) : (
            <EmptyState title="目前沒有已停用的平台管理員" />
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>提升既有帳號</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="platform-admin-inline-form"
            onSubmit={(event) => void run(() => promote(event))}
          >
            <Field>
              <label htmlFor="promote-user">可提升的帳號</label>
              <Select
                id="promote-user"
                value={promoteUserId}
                onChange={(event) => setPromoteUserId(event.target.value)}
                disabled={submitting}
                required
              >
                <option value="">請選擇</option>
                {candidates.map((candidate) => (
                  <option key={candidate.user_id} value={candidate.user_id}>
                    {candidate.display_name}（{candidate.username ?? "未設定"}）
                  </option>
                ))}
              </Select>
            </Field>
            <Button
              className="platform-admin-promote-submit"
              type="submit"
              disabled={
                submitting || !promoteUserId || policy?.available_slots === 0
              }
            >
              {submitting ? "處理中…" : "提升"}
            </Button>
          </form>
        </CardContent>
      </Card>
      <Dialog
        open={createOpen}
        title="建立平台管理員帳號"
        onClose={() => setCreateOpen(false)}
        className="account-dialog"
      >
        <form onSubmit={(event) => void run(() => createAdmin(event))}>
          <p className="dialog-description">
            帳號會立即建立為啟用中的平台管理員。
          </p>
          <Field>
            <label htmlFor="platform-username">帳號</label>
            <Input
              id="platform-username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              disabled={submitting}
              required
            />
          </Field>
          <Field>
            <label htmlFor="platform-display-name">顯示名稱</label>
            <Input
              id="platform-display-name"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              disabled={submitting}
              required
            />
          </Field>
          <Field>
            <label htmlFor="platform-password">暫時密碼</label>
            <Input
              id="platform-password"
              type="password"
              value={temporaryPassword}
              onChange={(event) => setTemporaryPassword(event.target.value)}
              disabled={submitting}
              required
            />
          </Field>
          <div className="dialog-actions">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setCreateOpen(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "處理中…" : "建立"}
            </Button>
          </div>
        </form>
      </Dialog>
      <Dialog
        open={replacementOpen}
        title="替換平台管理員"
        onClose={() => setReplacementOpen(false)}
        className="account-dialog"
      >
        <form onSubmit={(event) => void run(() => replace(event))}>
          <p className="dialog-description">
            一次確認完成新舊權限交接，不會產生部分完成狀態。
          </p>
          <Field>
            <label htmlFor="outgoing-admin">原管理員</label>
            <Select
              id="outgoing-admin"
              value={outgoingUserId}
              onChange={(event) => setOutgoingUserId(event.target.value)}
              disabled={submitting}
              required
            >
              {activeAdmins.map((admin) => (
                <option key={admin.user_id} value={admin.user_id}>
                  {admin.display_name}
                </option>
              ))}
            </Select>
          </Field>
          <Field>
            <label htmlFor="replacement-admin">替代帳號</label>
            <Select
              id="replacement-admin"
              value={replacementUserId}
              onChange={(event) => setReplacementUserId(event.target.value)}
              disabled={submitting}
              required
            >
              <option value="">請選擇</option>
              {candidates.map((candidate) => (
                <option key={candidate.user_id} value={candidate.user_id}>
                  {candidate.display_name}（{candidate.username ?? "未設定"}）
                </option>
              ))}
            </Select>
          </Field>
          <Field>
            <label htmlFor="replacement-reason">交接原因</label>
            <Input
              id="replacement-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              disabled={submitting}
              required
            />
          </Field>
          <div className="dialog-actions">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setReplacementOpen(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "處理中…" : "確認替換"}
            </Button>
          </div>
        </form>
      </Dialog>
      <Dialog
        open={pendingMutation !== null}
        title={pendingMutation?.title ?? "確認平台管理員異動"}
        role="alertdialog"
        onClose={() => setPendingMutation(null)}
        className="account-dialog"
      >
        <p className="dialog-description">
          {pendingMutation?.description ?? "請確認這項平台管理員異動。"}
        </p>
        <div className="dialog-actions">
          <Button
            type="button"
            variant="ghost"
            onClick={() => setPendingMutation(null)}
          >
            取消
          </Button>
          <Button
            type="button"
            onClick={() => void confirmPendingMutation()}
            disabled={submitting}
          >
            {submitting ? "處理中…" : (pendingMutation?.confirmLabel ?? "確認")}
          </Button>
        </div>
      </Dialog>
    </section>
  );
}
