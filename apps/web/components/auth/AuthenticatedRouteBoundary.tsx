"use client";

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  authFetch,
  clearAuth,
  getAccessToken,
  getSessionSource,
  type CurrentUser,
  type SessionSource,
} from "../../lib/auth";
import { decideRouteAccess, type EffectiveRole } from "../../lib/route-access";
import {
  ProtectedRouteState,
  type ProtectedRouteStateKind,
} from "./ProtectedRouteState";
import {
  VolunteerShelterContext,
  type VolunteerShelterContextValue,
} from "./VolunteerShelterContext";

export type BoundaryLoadResult = {
  profile: CurrentUser;
  context: {
    organization_id: string;
    organization_name: string;
    session_id: string;
  };
  sessionSource: SessionSource;
};

export type AuthenticatedRouteBoundaryProps = {
  area: "management" | "volunteer";
  pathname: string;
  children?: React.ReactNode;
  sessionSource?: SessionSource;
  loadContext?: () => Promise<BoundaryLoadResult>;
  onRedirect?: (
    destination: "/login" | "/volunteer-entry" | "/animal-confirmation",
  ) => void;
  onReenter?: () => void;
  onBack?: () => void;
  onRetry?: () => void;
  onContactManager?: () => void;
};

const EFFECTIVE_ROLES = new Set<EffectiveRole>([
  "VOLUNTEER",
  "STAFF",
  "SHELTER_ADMIN",
  "PLATFORM_ADMIN",
]);

function deriveEffectiveRole(
  profile: CurrentUser,
  organizationId: string,
): EffectiveRole | null {
  const platformRole = profile.user.platform_role;
  if (platformRole === "PLATFORM_ADMIN") return platformRole;
  const membership = profile.memberships.find(
    (item) =>
      item.organization_id === organizationId && item.status === "active",
  );
  if (!membership || !EFFECTIVE_ROLES.has(membership.role as EffectiveRole)) {
    return null;
  }
  if (membership.role !== "VOLUNTEER") return membership.role as EffectiveRole;

  const now = Date.now();
  const membershipStarts = membership.valid_from
    ? Date.parse(membership.valid_from)
    : Number.NaN;
  const membershipExpires = membership.expires_at
    ? Date.parse(membership.expires_at)
    : Number.NaN;
  const grant = membership.access_grant;
  const grantStarts = grant ? Date.parse(grant.valid_from) : Number.NaN;
  const grantExpires = grant ? Date.parse(grant.expires_at) : Number.NaN;
  const effectiveMembership =
    membership.status === "active" &&
    Number.isFinite(membershipStarts) &&
    Number.isFinite(membershipExpires) &&
    membershipStarts <= now &&
    now < membershipExpires;
  const effectiveGrant =
    grant?.membership_id === membership.id &&
    grant.organization_id === membership.organization_id &&
    grant.status === "active" &&
    Number.isFinite(grantStarts) &&
    Number.isFinite(grantExpires) &&
    grantStarts <= now &&
    now < grantExpires;
  return effectiveMembership && effectiveGrant ? "VOLUNTEER" : null;
}

async function defaultLoadContext(): Promise<BoundaryLoadResult> {
  const profileResponse = await authFetch("/v1/auth/me");
  if (!profileResponse.ok) throw profileResponse;
  const profile = (await profileResponse.json()) as CurrentUser;
  const contextResponse = await authFetch("/v1/auth/active-shelter-context");
  if (!contextResponse.ok) throw contextResponse;
  const context =
    (await contextResponse.json()) as BoundaryLoadResult["context"];
  return {
    profile,
    context,
    sessionSource: getSessionSource() ?? "local",
  };
}

function isUnauthorized(error: unknown): boolean {
  return error instanceof Response && error.status === 401;
}

export function AuthenticatedRouteBoundary({
  area,
  pathname,
  children,
  sessionSource,
  loadContext,
  onRedirect,
  onReenter,
  onBack,
  onRetry,
  onContactManager,
}: AuthenticatedRouteBoundaryProps) {
  const [state, setState] = useState<ProtectedRouteStateKind>("checking");
  const [shelterContext, setShelterContext] =
    useState<VolunteerShelterContextValue | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const runEpoch = useRef(0);
  const source = sessionSource ?? getSessionSource() ?? "local";
  const loader = loadContext ?? defaultLoadContext;

  const run = useCallback(async () => {
    const epoch = runEpoch.current + 1;
    runEpoch.current = epoch;
    const isCurrent = () => runEpoch.current === epoch;
    const updateState = (nextState: ProtectedRouteStateKind) => {
      if (isCurrent()) setState(nextState);
    };

    setShelterContext(null);
    if (!loadContext && !getAccessToken()) {
      clearAuth({ preserveLiffSession: source === "liff" });
      if (source === "liff") {
        updateState("re-entry");
      } else {
        updateState("redirecting");
        if (isCurrent()) onRedirect?.("/login");
      }
      return;
    }

    updateState("checking");
    let activeSource = source;
    try {
      const result = await loader();
      if (!isCurrent()) return;
      setShelterContext({
        organizationId: result.context.organization_id,
        organizationName: result.context.organization_name,
      });
      activeSource = result.sessionSource;
      const effectiveRole = deriveEffectiveRole(
        result.profile,
        result.context.organization_id,
      );
      const decision = decideRouteAccess({
        pathname,
        authState: "authenticated",
        role: effectiveRole,
        hasActiveContext: Boolean(result.context.organization_id),
      });
      if (decision.area !== area) {
        updateState("context-required");
        return;
      }
      updateState(decision.state);
      if (decision.state === "redirecting" && decision.destination) {
        onRedirect?.(decision.destination);
      }
    } catch (error) {
      if (!isCurrent()) return;
      if (isUnauthorized(error)) {
        setShelterContext(null);
        clearAuth({ preserveLiffSession: activeSource === "liff" });
        if (activeSource === "liff") {
          updateState("re-entry");
        } else {
          updateState("redirecting");
          if (isCurrent()) onRedirect?.("/login");
        }
      } else {
        setShelterContext(null);
        updateState("temporary-error");
      }
    }
  }, [area, loader, loadContext, onRedirect, pathname, source]);

  useEffect(() => {
    void run();
    return () => {
      runEpoch.current += 1;
    };
  }, [reloadKey, run]);

  const retry = useMemo(
    () =>
      onRetry ??
      (() => {
        setReloadKey((value) => value + 1);
      }),
    [onRetry],
  );

  return (
    <VolunteerShelterContext.Provider value={shelterContext}>
      <ProtectedRouteState
        state={state}
        onRetry={retry}
        onReenter={onReenter}
        onBack={onBack}
        onContactManager={onContactManager}
      >
        {children}
      </ProtectedRouteState>
    </VolunteerShelterContext.Provider>
  );
}
