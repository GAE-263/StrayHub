import {
  authFetch,
  clearAuth,
  getAccessToken,
  getSessionSource,
  storeSession,
} from "./auth";

type RefreshResponse = {
  access_token: string;
  refresh_token?: string;
  session_id: string;
};

let refreshInFlight:
  | { refreshToken: string; promise: Promise<RefreshResponse | null> }
  | undefined;

function refreshSession(refreshToken: string): Promise<RefreshResponse | null> {
  if (refreshInFlight?.refreshToken === refreshToken) {
    return refreshInFlight.promise;
  }
  let promise: Promise<RefreshResponse | null>;
  promise = fetch("/v1/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
    .then(async (response) => {
      if (!response.ok) return null;
      return (await response.json()) as RefreshResponse;
    })
    .catch(() => null)
    .finally(() => {
      if (refreshInFlight?.promise === promise) refreshInFlight = undefined;
    });
  refreshInFlight = { refreshToken, promise };
  return promise;
}

export async function apiFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
  options: { retryOnUnauthorized?: boolean } = {},
): Promise<Response> {
  const response = await authFetch(input, init, {
    emitUnauthorized: options.retryOnUnauthorized === false,
  });
  if (response.status !== 401 || options.retryOnUnauthorized === false) {
    if (response.status === 409 && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("strayhub:context-required"));
    }
    return response;
  }
  if (typeof window === "undefined") return response;
  const refreshToken = window.sessionStorage.getItem("refresh_token");
  if (!refreshToken || !getAccessToken()) {
    clearAuth({ preserveLiffSession: getSessionSource() === "liff" });
    window.dispatchEvent(new Event("strayhub:liff-unauthorized"));
    return response;
  }
  const refreshedSession = await refreshSession(refreshToken);
  if (!refreshedSession) {
    clearAuth({ preserveLiffSession: getSessionSource() === "liff" });
    window.dispatchEvent(new Event("strayhub:liff-unauthorized"));
    return response;
  }
  const currentRefreshToken = window.sessionStorage.getItem("refresh_token");
  if (
    currentRefreshToken !== refreshToken &&
    currentRefreshToken !== (refreshedSession.refresh_token ?? null)
  ) {
    return response;
  }
  storeSession(refreshedSession);
  const method = (
    init?.method ??
    (typeof Request !== "undefined" && input instanceof Request
      ? input.method
      : "GET")
  ).toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) return response;
  return authFetch(input, init);
}
