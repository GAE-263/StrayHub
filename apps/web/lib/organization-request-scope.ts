/** Client lifecycle only, never authorization. The server still owns tenant scope.
 * Management has no query cache: its state tree and every request use this
 * organization + generation identity, not an animal ID alone. A generation also
 * prevents an A → B → A response from becoming current again.
 */
export type OrganizationRequestScope = {
  organizationId: string;
  key: string;
  signal: AbortSignal;
};

let generation = 0;
let current:
  (OrganizationRequestScope & { controller: AbortController }) | null = null;

export function activateOrganizationRequests(
  organizationId: string,
): OrganizationRequestScope {
  if (current?.organizationId === organizationId && !current.signal.aborted)
    return current;
  current?.controller.abort();
  const controller = new AbortController();
  current = {
    organizationId,
    key: `${organizationId}:${++generation}`,
    controller,
    signal: controller.signal,
  };
  return current;
}

export function pauseOrganizationRequests(): void {
  // Keep the invalid identity installed: requests from old callbacks must not
  // become unscoped requests while the server context is being changed.
  current?.controller.abort();
}

export function clearOrganizationRequests(): void {
  pauseOrganizationRequests();
  current = null;
}

export function captureOrganizationRequestScope(
  input: RequestInfo | URL,
): OrganizationRequestScope | null {
  const url =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.href
        : input.url;
  // Context PUT/GET must still work while tenant requests are paused. Other
  // consumers outside ManagementLayout (including LIFF) retain their lifecycle.
  return new URL(url, "http://localhost").pathname.startsWith("/v1/auth/")
    ? null
    : current;
}

export function assertOrganizationRequestScope(
  scope: OrganizationRequestScope | null,
): void {
  if (scope && (scope !== current || scope.signal.aborted)) {
    throw new DOMException(
      "Organization request is no longer current",
      "AbortError",
    );
  }
}

export function organizationRequestSignal(
  scope: OrganizationRequestScope | null,
  caller?: AbortSignal | null,
) {
  if (!scope || !caller)
    return { signal: scope?.signal ?? caller, dispose: () => {} };
  // AbortSignal.any is not available in every supported webview/test runtime.
  const controller = new AbortController();
  const dispose = () => {
    scope.signal.removeEventListener("abort", abortScope);
    caller.removeEventListener("abort", abortCaller);
  };
  const abortScope = () => {
    controller.abort(scope.signal.reason);
    dispose();
  };
  const abortCaller = () => {
    controller.abort(caller.reason);
    dispose();
  };
  scope.signal.addEventListener("abort", abortScope, { once: true });
  caller.addEventListener("abort", abortCaller, { once: true });
  if (scope.signal.aborted) abortScope();
  if (caller.aborted) abortCaller();
  return { signal: controller.signal, dispose };
}
