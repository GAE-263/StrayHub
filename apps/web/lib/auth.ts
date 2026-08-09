export const ACCESS_TOKEN_KEY = "access_token";
export const REFRESH_TOKEN_KEY = "refresh_token";
export const SESSION_ID_KEY = "session_id";
export const ACTIVE_ORGANIZATION_ID_KEY = "active_organization_id";
export const ACTIVE_ORGANIZATION_CODE_KEY = "active_organization_code";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

export function clearAuth(): void {
  if (typeof window === "undefined") return;
  for (const key of [
    ACCESS_TOKEN_KEY,
    REFRESH_TOKEN_KEY,
    SESSION_ID_KEY,
    ACTIVE_ORGANIZATION_ID_KEY,
    ACTIVE_ORGANIZATION_CODE_KEY,
  ]) {
    window.sessionStorage.removeItem(key);
  }
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
