"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
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
import { canReviewVolunteerApplications } from "../../lib/management-capabilities";
import {
  activateOrganizationRequests,
  clearOrganizationRequests,
  pauseOrganizationRequests,
} from "../../lib/organization-request-scope";

type Props = { children: React.ReactNode };
type OrganizationSummary = { id: string; code: string; name: string };

export function resolveOrganizationLabel(
  organizations: OrganizationSummary[],
  organizationId: string | null,
  isPlatformGovernanceRoute: boolean,
): string {
  if (isPlatformGovernanceRoute) return "平台治理";
  return (
    organizations.find((organization) => organization.id === organizationId)
      ?.name ?? "未選擇收容所"
  );
}

export function ManagementLayout({ children }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const [profile, setProfile] = useState<CurrentUser | null>(null);
  const [organizationId, setOrganizationId] = useState<string | null>(null);
  const [organizations, setOrganizations] = useState<OrganizationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [contextSwitchError, setContextSwitchError] = useState("");
  const [contextUncertain, setContextUncertain] = useState(false);
  const [contextKey, setContextKey] = useState("");
  const contextLoad = useRef<AbortController | null>(null);
  const switching = useRef(false);

  useEffect(() => () => clearOrganizationRequests(), []);

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

  const loadContext = useCallback(
    async (signal: AbortSignal) => {
      if (!getAccessToken()) {
        router.replace("/login");
        return;
      }
      const profileResponse = await authFetch("/v1/auth/me", { signal });
      if (!profileResponse.ok) {
        if (profileResponse.status === 401) {
          clearAuth();
          router.replace("/login");
          return;
        }
        throw new Error("目前帳號尚未準備好管理工作台權限。");
      }
      const nextProfile = (await profileResponse.json()) as CurrentUser;
      signal.throwIfAborted();
      if (
        pathname === "/platform-admins" &&
        nextProfile.user.platform_role === "PLATFORM_ADMIN"
      ) {
        setProfile(nextProfile);
        setOrganizationId(null);
        setOrganizations([]);
        return;
      }
      const [contextResponse, organizationsResponse] = await Promise.all([
        authFetch("/v1/auth/active-shelter-context", { signal }),
        authFetch("/v1/organizations", { signal }),
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
      const organizationData = (await organizationsResponse.json()) as {
        items: Array<{ id: string; code: string; name: string }>;
      };
      signal.throwIfAborted();
      if (context.organization_id) {
        setContextKey(
          activateOrganizationRequests(context.organization_id).key,
        );
      }
      setProfile(nextProfile);
      setOrganizationId(context.organization_id ?? null);
      setOrganizations(organizationData.items);
    },
    [pathname, router],
  );

  useEffect(() => {
    if (switching.current) return;
    const controller = new AbortController();
    contextLoad.current = controller;
    void loadContext(controller.signal)
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted)
          setError(
            requestError instanceof Error
              ? requestError.message
              : "無法載入登入狀態",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => {
      controller.abort();
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
    if (
      switching.current ||
      nextOrganizationId === organizationId ||
      !organizationId
    )
      return;
    switching.current = true;
    contextLoad.current?.abort();
    pauseOrganizationRequests();
    // Unmount ALL tenant state (animal/report/medical/QR/dialogs) before PUT.
    // The old URL is the only selection retained, solely for a failed switch.
    flushSync(() => setLoading(true));
    setContextSwitchError("");
    const enterAnimalList = (confirmedOrganizationId: string) => {
      const next = organizations.find(
        (organization) => organization.id === confirmedOrganizationId,
      );
      try {
        if (next) {
          window.sessionStorage.setItem("active_organization_id", next.id);
          window.sessionStorage.setItem("active_organization_code", next.code);
        }
      } catch {
        // Hints are not authority; the new document re-reads the server context.
      }
      // Do not reload the old tenant's resource URL or reuse Next's route cache.
      // Keep requests paused/the subtree unmounted until the new document loads.
      window.location.replace("/animals");
    };
    try {
      const response = await authFetch("/v1/auth/active-shelter-context", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: nextOrganizationId }),
      });
      if (!response.ok) throw new Error("無法切換目前收容所");
      const confirmed = (await response.json()) as { organization_id: string };
      if (confirmed.organization_id !== nextOrganizationId)
        throw new Error("無法確認目前收容所");
      enterAnimalList(confirmed.organization_id);
    } catch (switchError: unknown) {
      // A lost PUT response is ambiguous: never remount A under a committed B.
      try {
        const response = await authFetch("/v1/auth/active-shelter-context");
        if (!response.ok) throw new Error("context unavailable");
        const confirmed = (await response.json()) as {
          organization_id?: string;
        };
        if (!confirmed.organization_id) throw new Error("context missing");
        if (confirmed.organization_id !== organizationId) {
          enterAnimalList(confirmed.organization_id);
          return;
        }
        setContextKey(activateOrganizationRequests(organizationId).key);
      } catch {
        setContextUncertain(true);
        setError("無法確認目前收容所，已暫停載入動物資料。請重新確認。");
        setLoading(false);
        return;
      }
      switching.current = false;
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
      <div>
        <ErrorState
          title="無法開啟管理工作台"
          description={error || "請回到登入頁選擇有效的收容所。"}
        />
        {contextUncertain ? (
          <button
            type="button"
            className="button"
            onClick={() => window.location.replace("/animals")}
          >
            重新確認收容所
          </button>
        ) : null}
      </div>
    );
  }

  const role = profile.user.platform_role ?? activeMembership?.role ?? "STAFF";
  const volunteerManagementPath =
    pathname.startsWith("/volunteers/") ||
    pathname === "/settings/volunteer-access";
  if (volunteerManagementPath && !canReviewVolunteerApplications(role)) {
    return (
      <ErrorState
        title="無法開啟志工管理"
        description="目前角色沒有志工報名、授權或通知管理權限。"
      />
    );
  }
  const organizationLabel = resolveOrganizationLabel(
    organizations,
    organizationId,
    isPlatformGovernanceRoute,
  );

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
        <main className="app-main" key={`${contextKey}:${pathname}`}>
          {contextSwitchError ? (
            <StatusBanner kind="warning">{contextSwitchError}</StatusBanner>
          ) : null}
          {children}
        </main>
      </div>
    </div>
  );
}
