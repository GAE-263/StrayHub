import type { EffectiveRole } from "./route-access";
import {
  assertOrganizationRequestScope,
  captureOrganizationRequestScope,
  organizationRequestSignal,
  type OrganizationRequestScope,
} from "./organization-request-scope";
import {
  clearLiffSession,
  LIFF_ENTRY_REFERENCE_KEY,
  LIFF_RECOVERY_EPOCH_KEY,
} from "./liff-session";

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
    user_id: string;
    role: string;
    status: string;
    valid_from?: string | null;
    expires_at?: string | null;
    access_grant?: {
      membership_id: string;
      organization_id: string;
      status: string;
      valid_from: string;
      expires_at: string;
    } | null;
  }>;
  public_exposure_profile?: "shared-demo-production" | "shared-demo-dev" | null;
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

export function clearAuth(
  options: { preserveLiffSession?: boolean } = {},
): void {
  if (typeof window === "undefined") return;
  const preserveLiffSession = options.preserveLiffSession === true;
  const preservedValues = preserveLiffSession
    ? [
        SESSION_SOURCE_KEY,
        LIFF_ENTRY_REFERENCE_KEY,
        LIFF_RECOVERY_EPOCH_KEY,
      ].map((key) => [key, window.sessionStorage.getItem(key)] as const)
    : [];
  let keyedRemovalFailed = false;
  const keys = [
    ACCESS_TOKEN_KEY,
    REFRESH_TOKEN_KEY,
    SESSION_ID_KEY,
    ACTIVE_ORGANIZATION_ID_KEY,
    ACTIVE_ORGANIZATION_CODE_KEY,
    ...(preserveLiffSession ? [] : [SESSION_SOURCE_KEY]),
  ];
  for (const key of keys) {
    try {
      window.sessionStorage.removeItem(key);
    } catch {
      keyedRemovalFailed = true;
    }
  }
  if (keyedRemovalFailed) {
    window.sessionStorage.clear();
    for (const [key, value] of preservedValues) {
      if (value !== null) window.sessionStorage.setItem(key, value);
    }
  }
  if (!preserveLiffSession) clearLiffSession();
  window.dispatchEvent(new Event("strayhub:auth-changed"));
}

export async function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
  options: {
    emitUnauthorized?: boolean;
    requestScope?: OrganizationRequestScope | null;
  } = {},
): Promise<Response> {
  const scope =
    options.requestScope === undefined
      ? captureOrganizationRequestScope(input)
      : options.requestScope;
  const callerSignal =
    init?.signal ??
    (typeof Request !== "undefined" && input instanceof Request
      ? input.signal
      : undefined);
  const checkCurrent = () => {
    assertOrganizationRequestScope(scope);
    callerSignal?.throwIfAborted();
  };
  checkCurrent();
  const { signal, dispose } = organizationRequestSignal(scope, callerSignal);
  const headers = new Headers(init?.headers);
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(input, { ...init, headers, signal });
    checkCurrent();
  } catch (error) {
    dispose();
    throw error;
  }
  // Fetch may have resolved headers before a switch, or an adapter may ignore
  // abort. Guard buffered body completion as well as headers before callers
  // publish downloads or other consumer side effects. Streaming response.body
  // deliberately remains unchanged until it has a separate lifecycle contract.
  if (scope) {
    for (const reader of [
      "json",
      "text",
      "blob",
      "arrayBuffer",
      "formData",
    ] as const) {
      const read = response[reader];
      if (typeof read !== "function") continue;
      Object.defineProperty(response, reader, {
        configurable: true,
        value: async () => {
          try {
            checkCurrent();
            const data = await read.call(response);
            checkCurrent();
            return data;
          } finally {
            dispose();
          }
        },
      });
    }
  }
  if (!response.ok || response.status === 204) dispose();
  if (
    response.status === 401 &&
    options.emitUnauthorized !== false &&
    typeof window !== "undefined"
  ) {
    window.dispatchEvent(new Event("strayhub:liff-unauthorized"));
  }
  return response;
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
