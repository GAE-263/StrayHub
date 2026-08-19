"use client";

import React, {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import { authFetch, type CurrentUser } from "../../../lib/auth";
import { Alert } from "../../../components/ui/alert";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../../components/ui/card";
import { Field } from "../../../components/ui/field";
import { Dialog } from "../../../components/ui/dialog";
import { Input } from "../../../components/ui/input";
import { Select } from "../../../components/ui/select";
import { Toast } from "../../../components/ui/toast";
import { MembershipPermissionDialog } from "../../../components/management/MembershipPermissionDialog";
import {
  EmptyState,
  LoadingState,
} from "../../../components/management/StateViews";

type Shelter = {
  id: string;
  code: string;
  name: string;
  status: "pending_setup" | "active" | "suspended";
  timezone: string;
  timezone_version: number;
};

type Membership = {
  id: string;
  organization_id: string;
  user_id: string;
  role: "SHELTER_ADMIN" | "STAFF" | "VOLUNTEER";
  status: "invited" | "active" | "disabled" | "expired" | "revoked";
  access_version: number;
  medical_care_access: boolean;
  username?: string | null;
  display_name?: string | null;
  archived_from_status?: string | null;
  archived_at?: string | null;
  archived_by_user_id?: string | null;
  volunteer_authorization_status?: "active" | "expired" | "revoked" | null;
};

type Area = {
  id: string;
  name: string;
  area_type: "area" | "cage";
  status: "active" | "inactive";
};

type MembershipChanges = Partial<
  Pick<Membership, "role" | "status" | "medical_care_access">
>;

type PendingMembershipChange = {
  membership: Membership;
  changes: MembershipChanges;
  operation: string;
  before: string;
  after: string;
  adminCountBefore: number;
  adminCountAfter: number;
};

type ToastMessage = {
  id: number;
  text: string;
};

const roleLabels: Record<Membership["role"], string> = {
  SHELTER_ADMIN: "收容所管理員",
  STAFF: "工作人員",
  VOLUNTEER: "志工",
};

const membershipStatusLabels: Record<string, string> = {
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
  invited: 4,
};

function sortMemberships(left: Membership, right: Membership) {
  const leftStatus =
    left.volunteer_authorization_status === "revoked"
      ? "revoked"
      : left.volunteer_authorization_status === "expired"
        ? "expired"
        : left.status;
  const rightStatus =
    right.volunteer_authorization_status === "revoked"
      ? "revoked"
      : right.volunteer_authorization_status === "expired"
        ? "expired"
        : right.status;
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
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}

export default function SheltersManagementPage() {
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [shelters, setShelters] = useState<Shelter[]>([]);
  const [sheltersLoading, setSheltersLoading] = useState(true);
  const [selectedShelterId, setSelectedShelterId] = useState("");
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [submittingAction, setSubmittingAction] = useState(false);
  const submittingActionRef = useRef(false);
  const [newShelterName, setNewShelterName] = useState("");
  const [organizationCode, setOrganizationCode] = useState("");
  const [initialAdminUsername, setInitialAdminUsername] = useState("");
  const [initialAdminPassword, setInitialAdminPassword] = useState("");
  const [accountUsername, setAccountUsername] = useState("");
  const [accountDisplayName, setAccountDisplayName] = useState("");
  const [accountPassword, setAccountPassword] = useState("");
  const [accountRole, setAccountRole] = useState<Membership["role"]>("STAFF");
  const [accountDialogOpen, setAccountDialogOpen] = useState(false);
  const [accountConfirmationOpen, setAccountConfirmationOpen] = useState(false);
  const [pendingMembershipChange, setPendingMembershipChange] =
    useState<PendingMembershipChange | null>(null);
  const [confirmingChange, setConfirmingChange] = useState(false);
  const [areaName, setAreaName] = useState("");
  const [areaType, setAreaType] = useState<Area["area_type"]>("area");
  const [message, setMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [toastMessage, setToastMessage] = useState<ToastMessage | null>(null);
  const selectedShelter = useMemo(
    () => shelters.find((shelter) => shelter.id === selectedShelterId),
    [shelters, selectedShelterId],
  );
  const currentRole = useMemo(() => {
    if (currentUser?.user.platform_role) return currentUser.user.platform_role;
    return (
      currentUser?.memberships.find(
        (membership) => membership.organization_id === selectedShelterId,
      )?.role ?? null
    );
  }, [currentUser, selectedShelterId]);
  const canManageOrganizations = currentRole === "PLATFORM_ADMIN";
  const canManageShelterSettings = ["PLATFORM_ADMIN", "SHELTER_ADMIN"].includes(
    currentRole ?? "",
  );
  const managementMemberships = useMemo(
    () =>
      memberships
        .filter((membership) => membership.role !== "VOLUNTEER")
        .sort(sortMemberships),
    [memberships],
  );
  const volunteerMemberships = useMemo(
    () =>
      memberships
        .filter((membership) => membership.role === "VOLUNTEER")
        .sort(sortMemberships),
    [memberships],
  );

  const request = useCallback(async <T,>(path: string, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    headers.set("Content-Type", "application/json");
    const response = await authFetch(path, {
      ...init,
      headers,
    });
    return responseData<T>(response);
  }, []);

  const loadShelters = useCallback(
    async (preferredId?: string) => {
      setSheltersLoading(true);
      try {
        const data = await request<{ items: Shelter[] }>("/v1/organizations");
        setShelters(data.items);
        setSelectedShelterId((current) => {
          const nextId = preferredId ?? current;
          if (data.items.some((shelter) => shelter.id === nextId)) {
            return nextId;
          }
          return data.items[0]?.id ?? "";
        });
      } finally {
        setSheltersLoading(false);
      }
    },
    [request],
  );

  const loadShelterDetails = useCallback(async () => {
    if (!selectedShelterId) {
      setDetailsLoading(false);
      return;
    }
    setDetailsLoading(true);
    try {
      const [membershipData, areaData] = await Promise.all([
        request<{ items: Membership[] }>(
          `/v1/organizations/${selectedShelterId}/memberships`,
        ),
        selectedShelter?.status === "active"
          ? request<{ items: Area[] }>(
              `/v1/organizations/${selectedShelterId}/areas`,
            )
          : Promise.resolve({ items: [] as Area[] }),
      ]);
      setMemberships(membershipData.items);
      setAreas(areaData.items);
    } finally {
      setDetailsLoading(false);
    }
  }, [request, selectedShelter, selectedShelterId]);

  useEffect(() => {
    void loadShelters().catch((error: Error) => setErrorMessage(error.message));
  }, [loadShelters]);

  useEffect(() => {
    void request<CurrentUser>("/v1/auth/me")
      .then(setCurrentUser)
      .catch((error: Error) => setErrorMessage(error.message));
  }, [request]);

  useEffect(() => {
    if (!canManageShelterSettings) {
      setMemberships([]);
      setAreas([]);
      setDetailsLoading(false);
      return;
    }
    void loadShelterDetails().catch((error: Error) =>
      setErrorMessage(error.message),
    );
  }, [
    canManageShelterSettings,
    loadShelterDetails,
    selectedShelterId,
    shelters,
  ]);

  const submit = async (event: FormEvent, action: () => Promise<void>) => {
    event.preventDefault();
    await runAction(action);
  };

  const runAction = async (action: () => Promise<void>) => {
    if (submittingActionRef.current) return;
    submittingActionRef.current = true;
    setSubmittingAction(true);
    setErrorMessage("");
    setMessage("");
    try {
      await action();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "操作失敗");
    } finally {
      submittingActionRef.current = false;
      setSubmittingAction(false);
    }
  };

  const showToast = (text: string) => {
    setToastMessage((current) => ({ id: (current?.id ?? 0) + 1, text }));
  };

  const activeAdminCount = useMemo(
    () =>
      memberships.filter(
        (membership) =>
          membership.role === "SHELTER_ADMIN" && membership.status === "active",
      ).length,
    [memberships],
  );

  const adminCountAfter = (
    membership: Membership,
    changes: MembershipChanges,
  ) => {
    const wasActiveAdmin =
      membership.role === "SHELTER_ADMIN" && membership.status === "active";
    const willBeActiveAdmin =
      (changes.role ?? membership.role) === "SHELTER_ADMIN" &&
      (changes.status ?? membership.status) === "active";
    return (
      activeAdminCount - (wasActiveAdmin ? 1 : 0) + (willBeActiveAdmin ? 1 : 0)
    );
  };

  const openMembershipChange = (
    membership: Membership,
    changes: MembershipChanges,
    operation: string,
  ) => {
    const nextRole = changes.role ?? membership.role;
    const nextStatus =
      operation === "封存成員"
        ? "archived"
        : (changes.status ?? membership.status);
    const nextMedical =
      changes.medical_care_access ?? membership.medical_care_access;
    setErrorMessage("");
    setMessage("");
    setPendingMembershipChange({
      membership,
      changes,
      operation,
      before: `${roleLabels[membership.role]}／${membershipStatusLabels[membership.status]}${membership.role === "STAFF" ? `／醫療資料權限${membership.medical_care_access ? "開啟" : "關閉"}` : ""}`,
      after: `${roleLabels[nextRole]}／${membershipStatusLabels[nextStatus] ?? nextStatus}${nextRole === "STAFF" ? `／醫療資料權限${nextMedical ? "開啟" : "關閉"}` : ""}`,
      adminCountBefore: activeAdminCount,
      adminCountAfter: adminCountAfter(membership, changes),
    });
  };

  const createShelter = async () => {
    const data = await request<Shelter>("/v1/organizations", {
      method: "POST",
      body: JSON.stringify({
        code: organizationCode,
        name: newShelterName,
        status: "pending_setup",
        initial_admin_username: initialAdminUsername,
        initial_admin_temporary_password: initialAdminPassword,
      }),
    });
    setMessage("收容所已建立，仍須平台管理員啟用後才能建立一般業務資料。");
    await loadShelters(data.id);
  };

  const activateShelter = async () => {
    if (!selectedShelterId) return;
    await request<Shelter>(`/v1/organizations/${selectedShelterId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "active" }),
    });
    setMessage("收容所已啟用。");
    await loadShelters(selectedShelterId);
  };

  const createAccount = async () => {
    const createdIdentity = accountDisplayName || accountUsername;
    const createdRole = accountRole;
    try {
      await request<Membership>(
        `/v1/organizations/${selectedShelterId}/accounts`,
        {
          method: "POST",
          body: JSON.stringify({
            username: accountUsername,
            display_name: accountDisplayName,
            temporary_password: accountPassword,
            role: accountRole,
          }),
        },
      );
    } catch (error) {
      setAccountPassword("");
      throw error;
    }
    setMessage("帳號與 Membership 已建立。");
    setAccountUsername("");
    setAccountDisplayName("");
    setAccountPassword("");
    setAccountDialogOpen(false);
    await loadShelterDetails();
    showToast(
      createdRole === "SHELTER_ADMIN"
        ? `已建立收容所管理員帳號「${createdIdentity}」`
        : `已建立${roleLabels[createdRole]}帳號「${createdIdentity}」`,
    );
  };

  const updateMembership = async (
    membership: Membership,
    changes: MembershipChanges,
  ) => {
    await request<Membership>(
      `/v1/organizations/${selectedShelterId}/memberships/${membership.id}`,
      {
        method: "PATCH",
        body: JSON.stringify({
          ...changes,
          expected_access_version: membership.access_version,
        }),
      },
    );
    await loadShelterDetails();
  };

  const archiveMembership = async (membership: Membership) => {
    await request<Membership>(
      `/v1/organizations/${selectedShelterId}/memberships/${membership.id}/archive`,
      {
        method: "POST",
        body: JSON.stringify({
          expected_access_version: membership.access_version,
        }),
      },
    );
    await loadShelterDetails();
  };

  const confirmMembershipChange = async () => {
    if (!pendingMembershipChange) return;
    const pending = pendingMembershipChange;
    setConfirmingChange(true);
    try {
      if (pending.operation === "封存成員") {
        await archiveMembership(pending.membership);
      } else {
        await updateMembership(pending.membership, pending.changes);
      }
      setPendingMembershipChange(null);
      showToast(
        `已完成${pending.operation}：「${pending.membership.display_name || pending.membership.username || "未命名使用者"}」`,
      );
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "操作失敗");
      if (error instanceof Error && error.message.includes("409")) {
        await loadShelterDetails();
      }
    } finally {
      setConfirmingChange(false);
    }
  };

  const submitAccountForm = (event: FormEvent) => {
    event.preventDefault();
    if (accountRole === "SHELTER_ADMIN") {
      setAccountDialogOpen(false);
      setAccountConfirmationOpen(true);
      return;
    }
    void runAction(createAccount);
  };

  const renderMembership = (membership: Membership) => {
    const identity =
      membership.display_name || membership.username || "未命名使用者";
    const isCurrentUser = membership.user_id === currentUser?.user.id;
    const authorizationStatus = membership.volunteer_authorization_status;
    const isAuthorizationInactive = ["expired", "revoked"].includes(
      authorizationStatus ?? "",
    );
    const canReenable =
      membership.status === "disabled" && !isAuthorizationInactive;
    const isMuted = membership.status !== "active" || isAuthorizationInactive;
    return (
      <li
        className={`membership-item${isMuted ? " membership-item-muted" : ""}`}
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
          <Badge>
            {membershipStatusLabels[membership.status] ?? membership.status}
          </Badge>
          {authorizationStatus && authorizationStatus !== "active" ? (
            <Badge>{volunteerAuthorizationLabels[authorizationStatus]}</Badge>
          ) : null}
        </div>
        <div className="membership-actions">
          <Select
            aria-label={`${identity} 角色`}
            value={membership.role}
            onChange={(event) =>
              openMembershipChange(
                membership,
                {
                  role: event.target.value as Membership["role"],
                },
                "調整角色",
              )
            }
          >
            <option value="SHELTER_ADMIN">收容所管理員</option>
            <option value="STAFF">工作人員</option>
            <option value="VOLUNTEER">志工</option>
          </Select>
          {membership.role === "STAFF" ? (
            <label className="membership-permission">
              <input
                type="checkbox"
                checked={membership.medical_care_access}
                aria-label={`${identity} 醫療資料權限`}
                onChange={(event) => {
                  const enabled = event.target.checked;
                  openMembershipChange(
                    membership,
                    { medical_care_access: enabled },
                    enabled ? "開啟醫療資料權限" : "停用醫療資料權限",
                  );
                }}
              />
              醫療資料權限
            </label>
          ) : null}
          <Button
            variant="secondary"
            type="button"
            disabled={membership.status !== "active"}
            onClick={() =>
              openMembershipChange(
                membership,
                { status: "disabled" },
                "停用成員",
              )
            }
          >
            停用
          </Button>
          {canReenable ? (
            <Button
              variant="secondary"
              type="button"
              onClick={() =>
                openMembershipChange(
                  membership,
                  { status: "active" },
                  "重新啟用成員",
                )
              }
            >
              重新啟用
            </Button>
          ) : null}
          <Button
            variant="secondary"
            type="button"
            disabled={isCurrentUser}
            onClick={() => openMembershipChange(membership, {}, "封存成員")}
          >
            封存
          </Button>
        </div>
      </li>
    );
  };

  const createArea = async () => {
    await request<Area>(`/v1/organizations/${selectedShelterId}/areas`, {
      method: "POST",
      body: JSON.stringify({ name: areaName, area_type: areaType }),
    });
    setMessage("Cage/Area 已建立。");
    setAreaName("");
    await loadShelterDetails();
  };

  return (
    <section
      className="shelter-management-page"
      aria-labelledby="shelter-management-title"
    >
      <div className="page-heading shelter-management-heading">
        <div>
          <span className="eyebrow">SHELTER ADMINISTRATION</span>
          <h1 id="shelter-management-title">權限管理</h1>
          <p>管理目前收容所的帳號角色、狀態與資料存取權限。</p>
        </div>
      </div>
      {errorMessage && (
        <Alert role="alert">授權或操作失敗：{errorMessage}</Alert>
      )}
      {message && <Alert role="status">{message}</Alert>}
      {toastMessage && (
        <Toast
          messageKey={toastMessage.id}
          onClose={() => setToastMessage(null)}
        >
          {toastMessage.text}
        </Toast>
      )}

      <Card aria-labelledby="shelter-list-title">
        <CardHeader>
          <CardTitle id="shelter-list-title">收容所</CardTitle>
        </CardHeader>
        <CardContent>
          {sheltersLoading ? (
            <LoadingState title="正在載入收容所…" />
          ) : shelters.length === 0 ? (
            <EmptyState title="目前沒有可管理的收容所" />
          ) : (
            <Field>
              <label htmlFor="selected-shelter">目前管理收容所</label>
              <Select
                id="selected-shelter"
                value={selectedShelterId}
                onChange={(event) => setSelectedShelterId(event.target.value)}
              >
                {shelters.map((shelter) => (
                  <option key={shelter.id} value={shelter.id}>
                    {shelter.name}（{shelter.status}）
                  </option>
                ))}
              </Select>
            </Field>
          )}
          {canManageOrganizations &&
            selectedShelter?.status === "pending_setup" && (
              <Button
                type="button"
                disabled={submittingAction}
                onClick={() => void runAction(activateShelter)}
              >
                {submittingAction ? "處理中…" : "啟用收容所"}
              </Button>
            )}
          {canManageOrganizations && (
            <form onSubmit={(event) => void submit(event, createShelter)}>
              <h3>建立收容所</h3>
              <Field>
                <label htmlFor="shelter-code">機構代碼</label>
                <Input
                  id="shelter-code"
                  value={organizationCode}
                  onChange={(event) => setOrganizationCode(event.target.value)}
                  disabled={submittingAction}
                  required
                />
              </Field>
              <Field>
                <label htmlFor="shelter-name">收容所名稱</label>
                <Input
                  id="shelter-name"
                  value={newShelterName}
                  onChange={(event) => setNewShelterName(event.target.value)}
                  disabled={submittingAction}
                  required
                />
              </Field>
              <Field>
                <label htmlFor="initial-admin-username">初始管理員帳號</label>
                <Input
                  id="initial-admin-username"
                  value={initialAdminUsername}
                  onChange={(event) =>
                    setInitialAdminUsername(event.target.value)
                  }
                  disabled={submittingAction}
                  required
                />
              </Field>
              <Field>
                <label htmlFor="initial-admin-password">
                  初始管理員暫時密碼
                </label>
                <Input
                  id="initial-admin-password"
                  type="password"
                  value={initialAdminPassword}
                  onChange={(event) =>
                    setInitialAdminPassword(event.target.value)
                  }
                  disabled={submittingAction}
                  required
                />
              </Field>
              <Button type="submit" disabled={submittingAction}>
                {submittingAction ? "處理中…" : "建立收容所"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>

      {canManageShelterSettings && (
        <Card aria-labelledby="account-list-title">
          <CardHeader className="membership-card-header">
            <div>
              <CardTitle id="account-list-title">帳號與權限</CardTitle>
              <p className="card-description">
                管理目前收容所的工作人員與志工。
              </p>
            </div>
            <div className="membership-header-actions">
              <Link
                className="ui-button ui-button-secondary"
                href="/shelters/archived"
              >
                查看已封存成員
              </Link>
              <Button
                type="button"
                disabled={selectedShelter?.status !== "active"}
                onClick={() => setAccountDialogOpen(true)}
              >
                建立帳號
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {detailsLoading ? (
              <LoadingState title="正在載入帳號與權限…" />
            ) : (
              <>
                <section
                  className="membership-section"
                  aria-labelledby="volunteer-title"
                >
                  <div className="membership-section-heading">
                    <div>
                      <h3 id="volunteer-title">志工</h3>
                      <p>依既有報名與限時授權流程管理</p>
                    </div>
                    <Badge>{volunteerMemberships.length} 人</Badge>
                  </div>
                  {volunteerMemberships.length > 0 ? (
                    <ul className="membership-list">
                      {volunteerMemberships.map(renderMembership)}
                    </ul>
                  ) : (
                    <p className="membership-empty">目前沒有志工。</p>
                  )}
                </section>
                <section
                  className="membership-section"
                  aria-labelledby="staff-title"
                >
                  <div className="membership-section-heading">
                    <div>
                      <h3 id="staff-title">工作人員</h3>
                    </div>
                    <Badge>{managementMemberships.length} 人</Badge>
                  </div>
                  {managementMemberships.length > 0 ? (
                    <ul className="membership-list">
                      {managementMemberships.map(renderMembership)}
                    </ul>
                  ) : (
                    <p className="membership-empty">目前沒有工作人員。</p>
                  )}
                </section>
              </>
            )}
          </CardContent>
        </Card>
      )}

      <Dialog
        open={accountDialogOpen}
        title="建立機構帳號"
        onClose={() => setAccountDialogOpen(false)}
        className="account-dialog"
      >
        <form onSubmit={submitAccountForm}>
          <p className="dialog-description">
            建立後，帳號會立即出現在對應的權限區塊。
          </p>
          <Field>
            <label htmlFor="account-username">帳號</label>
            <Input
              id="account-username"
              value={accountUsername}
              onChange={(event) => setAccountUsername(event.target.value)}
              disabled={submittingAction}
              required
            />
          </Field>
          <Field>
            <label htmlFor="account-display-name">顯示名稱</label>
            <Input
              id="account-display-name"
              value={accountDisplayName}
              onChange={(event) => setAccountDisplayName(event.target.value)}
              disabled={submittingAction}
              required
            />
          </Field>
          <Field>
            <label htmlFor="account-password">暫時密碼</label>
            <Input
              id="account-password"
              type="password"
              value={accountPassword}
              onChange={(event) => setAccountPassword(event.target.value)}
              disabled={submittingAction}
              required
            />
          </Field>
          <Field>
            <label htmlFor="account-role">角色</label>
            <Select
              id="account-role"
              value={accountRole}
              onChange={(event) =>
                setAccountRole(event.target.value as Membership["role"])
              }
              disabled={submittingAction}
            >
              <option value="SHELTER_ADMIN">收容所管理員</option>
              <option value="STAFF">工作人員</option>
              <option value="VOLUNTEER">志工</option>
            </Select>
          </Field>
          <div className="dialog-actions">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setAccountDialogOpen(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={submittingAction}>
              {submittingAction ? "處理中…" : "建立帳號"}
            </Button>
          </div>
        </form>
      </Dialog>

      <MembershipPermissionDialog
        open={Boolean(pendingMembershipChange)}
        shelterName={selectedShelter?.name}
        identity={
          pendingMembershipChange?.membership.display_name ||
          pendingMembershipChange?.membership.username ||
          "未命名使用者"
        }
        operation={pendingMembershipChange?.operation ?? "調整權限"}
        before={pendingMembershipChange?.before ?? ""}
        after={pendingMembershipChange?.after ?? ""}
        adminCountBefore={pendingMembershipChange?.adminCountBefore}
        adminCountAfter={pendingMembershipChange?.adminCountAfter}
        destructive={Boolean(
          pendingMembershipChange &&
          (pendingMembershipChange.operation.includes("停用") ||
            pendingMembershipChange.operation.includes("封存") ||
            pendingMembershipChange.adminCountAfter <
              pendingMembershipChange.adminCountBefore),
        )}
        onClose={() => setPendingMembershipChange(null)}
        onConfirm={() => void confirmMembershipChange()}
        confirming={confirmingChange}
      />

      {accountRole === "SHELTER_ADMIN" ? (
        <MembershipPermissionDialog
          open={accountConfirmationOpen}
          shelterName={selectedShelter?.name}
          identity={accountDisplayName || accountUsername || "新帳號"}
          operation="建立收容所管理員帳號"
          before="尚未建立"
          after="啟用中的 SHELTER_ADMIN"
          adminCountBefore={activeAdminCount}
          adminCountAfter={activeAdminCount + 1}
          onClose={() => {
            setAccountConfirmationOpen(false);
            setAccountDialogOpen(true);
          }}
          onConfirm={() => {
            setAccountConfirmationOpen(false);
            void runAction(createAccount);
          }}
        />
      ) : null}

      {canManageShelterSettings && (
        <Card aria-labelledby="area-list-title">
          <CardHeader>
            <CardTitle id="area-list-title">Cage / Area</CardTitle>
          </CardHeader>
          <CardContent>
            <ul>
              {areas.map((area) => (
                <li key={area.id}>
                  {area.name}（{area.area_type}／<Badge>{area.status}</Badge>）
                </li>
              ))}
            </ul>
            <form onSubmit={(event) => void submit(event, createArea)}>
              <Field>
                <label htmlFor="area-name">區域名稱</label>
                <Input
                  id="area-name"
                  value={areaName}
                  onChange={(event) => setAreaName(event.target.value)}
                  disabled={submittingAction}
                  required
                />
              </Field>
              <Field>
                <label htmlFor="area-type">類型</label>
                <Select
                  id="area-type"
                  value={areaType}
                  onChange={(event) =>
                    setAreaType(event.target.value as Area["area_type"])
                  }
                  disabled={submittingAction}
                >
                  <option value="area">Area</option>
                  <option value="cage">Cage</option>
                </Select>
              </Field>
              <Button
                type="submit"
                disabled={
                  submittingAction || selectedShelter?.status !== "active"
                }
              >
                {submittingAction ? "處理中…" : "建立區域"}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
    </section>
  );
}
