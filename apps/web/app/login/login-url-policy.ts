const FORBIDDEN_LOGIN_QUERY_KEYS = new Set([
  "username",
  "password",
  "temporary_password",
  "access_token",
  "refresh_token",
  "id_token",
  "authorization",
]);

type LoginQuery =
  URLSearchParams | Record<string, string | string[] | undefined>;

function normalizeQueryKey(key: string): string {
  return key.toLowerCase().replaceAll("-", "_");
}

export function hasForbiddenLoginQuery(query: LoginQuery): boolean {
  const keys =
    query instanceof URLSearchParams ? query.keys() : Object.keys(query);
  for (const key of keys) {
    if (FORBIDDEN_LOGIN_QUERY_KEYS.has(normalizeQueryKey(key))) return true;
  }
  return false;
}
