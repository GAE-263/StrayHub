import { authFetch, clearAuth, getAccessToken, storeSession } from "./auth";

type RefreshResponse = {
  access_token: string;
  refresh_token?: string;
  session_id: string;
};

export async function apiFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
  options: { retryOnUnauthorized?: boolean } = {},
): Promise<Response> {
  const response = await authFetch(input, init);
  if (response.status !== 401 || options.retryOnUnauthorized === false) {
    if (response.status === 409 && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("strayhub:context-required"));
    }
    return response;
  }
  if (typeof window === "undefined") return response;
  const refreshToken = window.sessionStorage.getItem("refresh_token");
  if (!refreshToken || !getAccessToken()) {
    clearAuth();
    return response;
  }
  const refreshResponse = await fetch("/v1/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!refreshResponse.ok) {
    clearAuth();
    return response;
  }
  storeSession((await refreshResponse.json()) as RefreshResponse);
  return authFetch(input, init);
}
