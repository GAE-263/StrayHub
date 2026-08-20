"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AppHeader } from "./AppHeader";
import { AppSidebar } from "./AppSidebar";
import { MobileNavigation } from "./MobileNavigation";
import {
  clearAuth,
  authFetch,
  getAccessToken,
  type CurrentUser,
} from "../../lib/auth";
import { ErrorState, LoadingState } from "./StateViews";
import { StatusBanner } from "./StatusBanner";

type Props = { children: React.ReactNode };

export function ManagementLayout({ children }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const [profile, setProfile] = useState<CurrentUser | null>(null);
  const [organizationId, setOrganizationId] = useState<string | null>(null);
  const [organizations, setOrganizations] = useState<
    Array<{ id: string; code: string; name: string }>
  >([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [contextSwitchError, setContextSwitchError] = useState("");

  useEffect(() => {
    const showContextRequired = () =>
      setError("目前頁面需要重新選擇目前收容所。");
    window.addEventListener("strayhub:context-required", showContextRequired);
    return () =>
      window.removeEventListener(
        "strayhub:context-required",
        showContextRequired,
      );
  }, []);

  const loadContext = useCallback(async () => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    const profileResponse = await authFetch("/v1/auth/me");
    if (!profileResponse.ok) {
      if (profileResponse.status === 401) {
        clearAuth();
        router.replace("/login");
        return;
      }
      throw new Error("目前帳號尚未準備好管理工作台權限。");
    }
    const nextProfile = (await profileResponse.json()) as CurrentUser;
    setProfile(nextProfile);
    if (
      pathname === "/platform-admins" &&
      nextProfile.user.platform_role === "PLATFORM_ADMIN"
    ) {
      setOrganizationId(null);
      setOrganizations([]);
      return;
    }
    const [contextResponse, organizationsResponse] = await Promise.all([
      authFetch("/v1/auth/active-shelter-context"),
      authFetch("/v1/organizations"),
    ]);
    if (!contextResponse.ok || !organizationsResponse.ok) {
      if (
        contextResponse.status === 401 ||
        organizationsResponse.status === 401
      ) {
        clearAuth();
        router.replace("/login");
        return;
      }
      throw new Error("目前帳號尚未準備好管理工作台權限。");
    }
    const context = (await contextResponse.json()) as {
      organization_id?: string;
    };
    setOrganizationId(context.organization_id ?? null);
    const organizationData = (await organizationsResponse.json()) as {
      items: Array<{ id: string; code: string; name: string }>;
    };
    setOrganizations(organizationData.items);
  }, [pathname, router]);

  useEffect(() => {
    let cancelled = false;
    void loadContext()
      .catch((requestError: unknown) => {
        if (!cancelled)
          setError(
            requestError instanceof Error
              ? requestError.message
              : "無法載入登入狀態",
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadContext, pathname]);

  const activeMembership = useMemo(
    () =>
      profile?.memberships.find(
        (membership) => membership.organization_id === organizationId,
      ),
    [organizationId, profile],
  );

  const isPlatformGovernanceRoute = pathname === "/platform-admins";
  const isPlatformAdmin = profile?.user.platform_role === "PLATFORM_ADMIN";

  const logout = async () => {
    try {
      await authFetch("/v1/auth/logout", { method: "POST" });
    } finally {
      clearAuth();
      router.replace("/login");
    }
  };

  const switchOrganization = async (nextOrganizationId: string) => {
    if (nextOrganizationId === organizationId) return;
    setLoading(true);
    setContextSwitchError("");
    try {
      const response = await authFetch("/v1/auth/active-shelter-context", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: nextOrganizationId }),
      });
      if (!response.ok) throw new Error("無法切換目前收容所");
      const next = organizations.find(
        (organization) => organization.id === nextOrganizationId,
      );
      if (next && typeof window !== "undefined") {
        window.sessionStorage.setItem("active_organization_id", next.id);
        window.sessionStorage.setItem("active_organization_code", next.code);
      }
      window.location.reload();
    } catch (switchError: unknown) {
      setContextSwitchError(
        switchError instanceof Error
          ? switchError.message
          : "目前收容所切換失敗",
      );
      setLoading(false);
    }
  };

  if (loading)
    return (
      <LoadingState
        title="正在確認工作台權限…"
        description="重新驗證登入狀態與成員資格。"
      />
    );
  if (
    error ||
    !profile ||
    (!organizationId && !(isPlatformGovernanceRoute && isPlatformAdmin))
  ) {
    return (
      <ErrorState
        title="無法開啟管理工作台"
        description={error || "請回到登入頁選擇有效的收容所。"}
      />
    );
  }

  const role = profile.user.platform_role ?? activeMembership?.role ?? "STAFF";
  const volunteerManagementPath =
    pathname.startsWith("/volunteers/") ||
    pathname === "/settings/volunteer-access";
  if (
    volunteerManagementPath &&
    !["PLATFORM_ADMIN", "SHELTER_ADMIN"].includes(role)
  ) {
    return (
      <ErrorState
        title="無法開啟志工管理"
        description="目前角色沒有志工報名、授權或通知管理權限。"
      />
    );
  }
  const organizationLabel = isPlatformGovernanceRoute
    ? "平台治理"
    : typeof window !== "undefined"
      ? (window.sessionStorage.getItem("active_organization_code") ??
        organizationId?.slice(0, 8) ??
        "未選擇收容所")
      : (organizationId?.slice(0, 8) ?? "未選擇收容所");

  return (
    <div className="app-frame">
      <AppHeader
        displayName={
          profile.user.display_name ?? profile.user.username ?? "使用者"
        }
        organizationLabel={organizationLabel}
        organizations={isPlatformGovernanceRoute ? [] : organizations}
        activeOrganizationId={organizationId ?? ""}
        onSwitchOrganization={(nextOrganizationId) =>
          void switchOrganization(nextOrganizationId)
        }
        onLogout={() => void logout()}
        mobileNavigation={
          <MobileNavigation role={role} onLogout={() => void logout()} />
        }
      />
      <div className="app-body">
        <AppSidebar role={role} />
        <main className="app-main">
          {contextSwitchError ? (
            <StatusBanner kind="warning">{contextSwitchError}</StatusBanner>
          ) : null}
          {children}
        </main>
      </div>
    </div>
  );
}
