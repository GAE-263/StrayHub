import type { EffectiveRole } from "./route-access";
import { clearLiffSession } from "./liff-session";

export const ACCESS_TOKEN_KEY = "access_token";
export const REFRESH_TOKEN_KEY = "refresh_token";
export const SESSION_ID_KEY = "session_id";
export const ACTIVE_ORGANIZATION_ID_KEY = "active_organization_id";
export const ACTIVE_ORGANIZATION_CODE_KEY = "active_organization_code";
export const SESSION_SOURCE_KEY = "session_source";

export type SessionSource = "local" | "liff";

export type AuthOrganization = {
  id: string;
  code: string;
  name: string;
  role: string;
};

export type CurrentUser = {
  user: {
    id: string;
    username?: string | null;
    display_name?: string | null;
    platform_role?: string | null;
    status: string;
  };
  memberships: Array<{
    id: string;
    organization_id: string;
    role: string;
    status: string;
  }>;
};

export type AuthenticatedRouteContext = {
  profile: CurrentUser;
  organizationId: string;
  organizationName: string | null;
  effectiveRole: EffectiveRole | null;
  sessionSource: SessionSource;
};

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

export function clearAuth(): void {
  if (typeof window === "undefined") return;
  let keyedRemovalFailed = false;
  for (const key of [
    ACCESS_TOKEN_KEY,
    REFRESH_TOKEN_KEY,
    SESSION_ID_KEY,
    ACTIVE_ORGANIZATION_ID_KEY,
    ACTIVE_ORGANIZATION_CODE_KEY,
    SESSION_SOURCE_KEY,
  ]) {
    try {
      window.sessionStorage.removeItem(key);
    } catch {
      keyedRemovalFailed = true;
    }
  }
  if (keyedRemovalFailed) {
    window.sessionStorage.clear();
  }
  clearLiffSession();
  window.dispatchEvent(new Event("strayhub:auth-changed"));
}

export function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const headers = new Headers(init?.headers);
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(input, { ...init, headers });
}

export function storeSession(session: {
  access_token: string;
  refresh_token?: string;
  session_id: string;
}): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(ACCESS_TOKEN_KEY, session.access_token);
  if (session.refresh_token) {
    window.sessionStorage.setItem(REFRESH_TOKEN_KEY, session.refresh_token);
  }
  window.sessionStorage.setItem(SESSION_ID_KEY, session.session_id);
  window.dispatchEvent(new Event("strayhub:auth-changed"));
}

export function getSessionSource(): SessionSource | null {
  if (typeof window === "undefined") return null;
  try {
    const source = window.sessionStorage.getItem(SESSION_SOURCE_KEY);
    return source === "local" || source === "liff" ? source : null;
  } catch {
    return null;
  }
}

export function storeSessionSource(source: SessionSource): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(SESSION_SOURCE_KEY, source);
  } catch {
    // Source is a workflow hint and never an authorization decision.
  }
}

export function storeActiveOrganization(organization: AuthOrganization): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(ACTIVE_ORGANIZATION_ID_KEY, organization.id);
  window.sessionStorage.setItem(
    ACTIVE_ORGANIZATION_CODE_KEY,
    organization.code,
  );
  window.dispatchEvent(new Event("strayhub:auth-changed"));
}
