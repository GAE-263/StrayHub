export function unsafeQueryReader(searchParams: URLSearchParams) {
  return searchParams.get("password");
}
