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
  username?: string | null;
  display_name?: string | null;
  archived_from_status?: string | null;
  archived_at?: string | null;
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
  const [selectedShelterId, setSelectedShelterId] = useState("");
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

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
    const data = await request<{ items: Shelter[] }>("/v1/organizations");
    setShelters(data.items);
    setSelectedShelterId((current) =>
      data.items.some((shelter) => shelter.id === current)
        ? current
        : (data.items[0]?.id ?? ""),
    );
  }, [request]);

  const loadArchivedMemberships = useCallback(async () => {
    if (!selectedShelterId) return;
    const data = await request<{ items: Membership[] }>(
      `/v1/organizations/${selectedShelterId}/memberships/archived`,
    );
    setMemberships(data.items);
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

  const restoreMembership = async (membershipId: string) => {
    setErrorMessage("");
    setMessage("");
    try {
      await request<Membership>(
        `/v1/organizations/${selectedShelterId}/memberships/${membershipId}/restore`,
        { method: "POST" },
      );
      setMessage("成員已恢復，請回到權限管理查看目前狀態。");
      await loadArchivedMemberships();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "操作失敗");
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
  const managementMemberships = filteredMemberships.filter(
    (membership) => membership.role !== "VOLUNTEER",
  );
  const volunteerMemberships = filteredMemberships.filter(
    (membership) => membership.role === "VOLUNTEER",
  );

  const renderMembership = (membership: Membership) => {
    const identity =
      membership.display_name || membership.username || "未命名使用者";
    return (
      <li
        className="membership-item archived-membership-item"
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
        </div>
        <div className="membership-actions">
          <Button
            type="button"
            onClick={() => void restoreMembership(membership.id)}
          >
            恢復成員
          </Button>
        </div>
      </li>
    );
  };

  return (
    <main className="shelter-management-page" aria-labelledby="archived-title">
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
      <Card aria-labelledby="archived-list-title">
        <CardHeader className="membership-card-header">
          <div>
            <CardTitle id="archived-list-title">封存資料</CardTitle>
            <p className="card-description">
              封存資料不會出現在日常權限管理清單。
            </p>
          </div>
          <div className="membership-header-actions">
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
          <section
            className="membership-section"
            aria-labelledby="archived-staff-title"
          >
            <div className="membership-section-heading">
              <div>
                <h2 id="archived-staff-title">管理人員</h2>
                <p>收容所管理員與工作人員</p>
              </div>
              <Badge>{managementMemberships.length} 人</Badge>
            </div>
            {managementMemberships.length > 0 ? (
              <ul className="membership-list">
                {managementMemberships.map(renderMembership)}
              </ul>
            ) : (
              <p className="membership-empty">
                目前沒有符合條件的封存管理人員。
              </p>
            )}
          </section>
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
              <p className="membership-empty">目前沒有符合條件的封存志工。</p>
            )}
          </section>
        </CardContent>
      </Card>
    </main>
  );
}
