export const DEFAULT_TIMELINE_TIMEZONE = "Asia/Taipei";

/**
 * Timeline timestamps arrive as UTC ISO strings; showing them raw puts the
 * wrong wall-clock time in front of shelter staff.
 */
export function localDateTime(
  value: string | null | undefined,
  timezone: string,
) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  try {
    return new Intl.DateTimeFormat("zh-TW", {
      timeZone: timezone,
      dateStyle: "short",
      timeStyle: "short",
    }).format(parsed);
  } catch {
    return new Intl.DateTimeFormat("zh-TW", {
      timeZone: DEFAULT_TIMELINE_TIMEZONE,
      dateStyle: "short",
      timeStyle: "short",
    }).format(parsed);
  }
}
