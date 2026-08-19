"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Alert } from "../../../../components/ui/alert";
import { Badge } from "../../../../components/ui/badge";
import { Button } from "../../../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../../../components/ui/card";
import { Field } from "../../../../components/ui/field";
import { Input } from "../../../../components/ui/input";
import { Select } from "../../../../components/ui/select";
import { Toast } from "../../../../components/ui/toast";
import { MembershipPermissionDialog } from "../../../../components/management/MembershipPermissionDialog";
import {
  EmptyState,
  LoadingState,
} from "../../../../components/management/StateViews";
import { authFetch, type CurrentUser } from "../../../../lib/auth";

type Shelter = {
  id: string;
  name: string;
  status: "pending_setup" | "active" | "suspended";
};

type Membership = {
  id: string;
  user_id: string;
  role: "SHELTER_ADMIN" | "STAFF" | "VOLUNTEER";
  status: "archived";
  access_version: number;
  username?: string | null;
  display_name?: string | null;
  archived_from_status?: string | null;
  archived_at?: string | null;
  volunteer_authorization_status?: "active" | "expired" | "revoked" | null;
};

type ActiveMembership = {
  role: Membership["role"];
  status: string;
};

const roleLabels: Record<Membership["role"], string> = {
  SHELTER_ADMIN: "收容所管理員",
  STAFF: "工作人員",
  VOLUNTEER: "志工",
};
const statusLabels: Record<string, string> = {
  invited: "待接受",
  active: "啟用中",
  disabled: "已停用",
  expired: "已過期",
  revoked: "已撤銷",
};

const volunteerAuthorizationLabels: Record<string, string> = {
  expired: "授權已到期",
  revoked: "授權已撤銷",
};

const membershipStatusOrder: Record<string, number> = {
  active: 0,
  disabled: 1,
  expired: 2,
  revoked: 3,
};

function sortArchivedMemberships(left: Membership, right: Membership) {
  const leftStatus =
    left.volunteer_authorization_status === "revoked"
      ? "revoked"
      : left.volunteer_authorization_status === "expired"
        ? "expired"
        : (left.archived_from_status ?? "disabled");
  const rightStatus =
    right.volunteer_authorization_status === "revoked"
      ? "revoked"
      : right.volunteer_authorization_status === "expired"
        ? "expired"
        : (right.archived_from_status ?? "disabled");
  const statusOrder =
    (membershipStatusOrder[leftStatus] ?? 99) -
    (membershipStatusOrder[rightStatus] ?? 99);
  if (statusOrder !== 0) return statusOrder;
  if (left.role !== right.role) {
    return left.role === "SHELTER_ADMIN" ? -1 : 1;
  }
  return (left.display_name ?? left.username ?? "").localeCompare(
    right.display_name ?? right.username ?? "",
  );
}

async function responseData<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = "操作失敗";
    try {
      const body = (await response.json()) as { message?: string };
      detail = body.message ?? detail;
    } catch {
      // Keep a safe generic message when the server response is not JSON.
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export default function ArchivedShelterMembershipsPage() {
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [shelters, setShelters] = useState<Shelter[]>([]);
  const [sheltersLoading, setSheltersLoading] = useState(true);
  const [selectedShelterId, setSelectedShelterId] = useState("");
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [membershipsLoading, setMembershipsLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [toastMessage, setToastMessage] = useState("");
  const [activeAdminCount, setActiveAdminCount] = useState(0);
  const [pendingRestore, setPendingRestore] = useState<Membership | null>(null);
  const [confirmingRestore, setConfirmingRestore] = useState(false);

  const request = useCallback(async <T,>(path: string, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    headers.set("Content-Type", "application/json");
    return responseData<T>(await authFetch(path, { ...init, headers }));
  }, []);

  const currentRole = useMemo(() => {
    if (currentUser?.user.platform_role) return currentUser.user.platform_role;
    return (
      currentUser?.memberships.find(
        (membership) => membership.organization_id === selectedShelterId,
      )?.role ?? null
    );
  }, [currentUser, selectedShelterId]);
  const canManage = ["PLATFORM_ADMIN", "SHELTER_ADMIN"].includes(
    currentRole ?? "",
  );

  const loadShelters = useCallback(async () => {
    setSheltersLoading(true);
    try {
      const data = await request<{ items: Shelter[] }>("/v1/organizations");
      setShelters(data.items);
      setSelectedShelterId((current) =>
        data.items.some((shelter) => shelter.id === current)
          ? current
          : (data.items[0]?.id ?? ""),
      );
    } finally {
      setSheltersLoading(false);
    }
  }, [request]);

  const loadArchivedMemberships = useCallback(async () => {
    if (!selectedShelterId) {
      setMembershipsLoading(false);
      return;
    }
    setMembershipsLoading(true);
    try {
      const [data, activeData] = await Promise.all([
        request<{ items: Membership[] }>(
          `/v1/organizations/${selectedShelterId}/memberships/archived`,
        ),
        request<{ items: ActiveMembership[] }>(
          `/v1/organizations/${selectedShelterId}/memberships`,
        ),
      ]);
      setMemberships(data.items);
      setActiveAdminCount(
        activeData.items.filter(
          (membership) =>
            membership.role === "SHELTER_ADMIN" &&
            membership.status === "active",
        ).length,
      );
    } finally {
      setMembershipsLoading(false);
    }
  }, [request, selectedShelterId]);

  useEffect(() => {
    void Promise.all([
      loadShelters(),
      request<CurrentUser>("/v1/auth/me").then(setCurrentUser),
    ]).catch((error: Error) => setErrorMessage(error.message));
  }, [loadShelters, request]);

  useEffect(() => {
    if (!canManage) {
      setMemberships([]);
      return;
    }
    void loadArchivedMemberships().catch((error: Error) =>
      setErrorMessage(error.message),
    );
  }, [canManage, loadArchivedMemberships, selectedShelterId]);

  const restoreMembership = async (membership: Membership) => {
    setErrorMessage("");
    setMessage("");
    try {
      await request<Membership>(
        `/v1/organizations/${selectedShelterId}/memberships/${membership.id}/restore`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_access_version: membership.access_version,
          }),
        },
      );
      await loadArchivedMemberships();
      setToastMessage(
        `已恢復成員「${membership.display_name || membership.username || "未命名使用者"}」`,
      );
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "操作失敗");
    }
  };

  const confirmRestore = async () => {
    if (!pendingRestore) return;
    setConfirmingRestore(true);
    try {
      await restoreMembership(pendingRestore);
      setPendingRestore(null);
    } finally {
      setConfirmingRestore(false);
    }
  };

  const filteredMemberships = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return memberships;
    return memberships.filter((membership) =>
      [membership.display_name, membership.username]
        .filter(Boolean)
        .some((value) => value!.toLowerCase().includes(needle)),
    );
  }, [memberships, search]);
  const managementMemberships = filteredMemberships
    .filter((membership) => membership.role !== "VOLUNTEER")
    .sort(sortArchivedMemberships);
  const volunteerMemberships = filteredMemberships
    .filter((membership) => membership.role === "VOLUNTEER")
    .sort(sortArchivedMemberships);

  const renderMembership = (membership: Membership) => {
    const identity =
      membership.display_name || membership.username || "未命名使用者";
    return (
      <li
        className="membership-item membership-item-muted archived-membership-item"
        key={membership.id}
      >
        <div className="membership-identity">
          <strong>{identity}</strong>
          {membership.username && (
            <span className="membership-username">
              帳號：{membership.username}
            </span>
          )}
        </div>
        <div className="membership-meta">
          <Badge>{roleLabels[membership.role]}</Badge>
          <Badge>已封存</Badge>
          {membership.archived_from_status && (
            <span className="membership-history">
              封存前：
              {statusLabels[membership.archived_from_status] ??
                membership.archived_from_status}
            </span>
          )}
          {membership.volunteer_authorization_status &&
          membership.volunteer_authorization_status !== "active" ? (
            <Badge>
              {
                volunteerAuthorizationLabels[
                  membership.volunteer_authorization_status
                ]
              }
            </Badge>
          ) : null}
        </div>
        <div className="membership-actions">
          <Button type="button" onClick={() => setPendingRestore(membership)}>
            恢復成員
          </Button>
        </div>
      </li>
    );
  };

  return (
    <section
      className="shelter-management-page"
      aria-labelledby="archived-title"
    >
      <div className="page-heading shelter-management-heading">
        <div>
          <span className="eyebrow">SHELTER ADMINISTRATION</span>
          <h1 id="archived-title">已封存成員</h1>
          <p>查詢目前收容所已封存的帳號與 Membership，必要時恢復權限。</p>
        </div>
        <Link className="ui-button ui-button-secondary" href="/shelters">
          返回權限管理
        </Link>
      </div>
      {errorMessage && (
        <Alert role="alert">授權或操作失敗：{errorMessage}</Alert>
      )}
      {message && <Alert role="status">{message}</Alert>}
      {toastMessage && <Toast>{toastMessage}</Toast>}
      <Card aria-labelledby="archived-list-title">
        <CardHeader className="membership-card-header">
          <div>
            <CardTitle id="archived-list-title">封存資料</CardTitle>
            <p className="card-description">
              封存資料不會出現在日常權限管理清單。
            </p>
          </div>
          <div className="membership-header-actions">
            {sheltersLoading ? (
              <LoadingState title="正在載入收容所…" />
            ) : shelters.length === 0 ? (
              <EmptyState title="目前沒有可管理的收容所" />
            ) : (
              <Field>
                <label htmlFor="archived-shelter">目前管理收容所</label>
                <Select
                  id="archived-shelter"
                  value={selectedShelterId}
                  onChange={(event) => setSelectedShelterId(event.target.value)}
                >
                  {shelters.map((shelter) => (
                    <option key={shelter.id} value={shelter.id}>
                      {shelter.name}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            <Field>
              <label htmlFor="archived-search">搜尋姓名或帳號</label>
              <Input
                id="archived-search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="例如：local-staff-a"
              />
            </Field>
          </div>
        </CardHeader>
        <CardContent>
          {membershipsLoading ? (
            <LoadingState title="正在載入封存成員…" />
          ) : (
            <>
              <section
                className="membership-section"
                aria-labelledby="archived-volunteer-title"
              >
                <div className="membership-section-heading">
                  <div>
                    <h2 id="archived-volunteer-title">志工</h2>
                    <p>封存的志工授權仍保留歷史紀錄</p>
                  </div>
                  <Badge>{volunteerMemberships.length} 人</Badge>
                </div>
                {volunteerMemberships.length > 0 ? (
                  <ul className="membership-list">
                    {volunteerMemberships.map(renderMembership)}
                  </ul>
                ) : (
                  <p className="membership-empty">
                    目前沒有符合條件的封存志工。
                  </p>
                )}
              </section>
              <section
                className="membership-section"
                aria-labelledby="archived-staff-title"
              >
                <div className="membership-section-heading">
                  <div>
                    <h2 id="archived-staff-title">工作人員</h2>
                  </div>
                  <Badge>{managementMemberships.length} 人</Badge>
                </div>
                {managementMemberships.length > 0 ? (
                  <ul className="membership-list">
                    {managementMemberships.map(renderMembership)}
                  </ul>
                ) : (
                  <p className="membership-empty">
                    目前沒有符合條件的封存工作人員。
                  </p>
                )}
              </section>
            </>
          )}
        </CardContent>
      </Card>
      <MembershipPermissionDialog
        open={Boolean(pendingRestore)}
        shelterName={
          shelters.find((shelter) => shelter.id === selectedShelterId)?.name
        }
        identity={
          pendingRestore?.display_name ||
          pendingRestore?.username ||
          "未命名使用者"
        }
        operation="恢復成員"
        before="已封存"
        after={
          pendingRestore?.role === "SHELTER_ADMIN" &&
          pendingRestore.archived_from_status === "active"
            ? "啟用中的收容所管理員"
            : "恢復封存前狀態"
        }
        adminCountBefore={activeAdminCount}
        adminCountAfter={
          activeAdminCount +
          (pendingRestore?.role === "SHELTER_ADMIN" &&
          pendingRestore.archived_from_status === "active"
            ? 1
            : 0)
        }
        authorizationImpact={
          pendingRestore?.volunteer_authorization_status === "expired" ||
          pendingRestore?.volunteer_authorization_status === "revoked"
            ? "志工授權已過期或撤銷，恢復 Membership 不會繞過授權流程。"
            : undefined
        }
        onClose={() => setPendingRestore(null)}
        onConfirm={() => void confirmRestore()}
        confirming={confirmingRestore}
      />
    </section>
  );
}
