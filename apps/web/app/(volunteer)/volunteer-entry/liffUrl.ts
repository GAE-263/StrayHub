export function scrubLegacyIdToken(
  entryUrl: URL,
  replaceHistory = (path: string) =>
    window.history.replaceState(window.history.state, "", path),
  replaceLocation = (url: string) => window.location.replace(url),
): boolean {
  if (!entryUrl.searchParams.has("id_token")) return true;
  entryUrl.searchParams.delete("id_token");
  const safePath = `${entryUrl.pathname}${entryUrl.search}${entryUrl.hash}`;
  try {
    replaceHistory(safePath);
    return true;
  } catch {
    try {
      replaceLocation(entryUrl.toString());
    } catch {
      // Both browser navigation APIs can be unavailable for an inactive document.
    }
    return false;
  }
}
