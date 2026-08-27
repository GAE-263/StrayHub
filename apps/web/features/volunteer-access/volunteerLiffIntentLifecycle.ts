import {
  parseVolunteerLiffEntryIntent,
  type VolunteerLiffEntryIntent,
} from "./volunteerLiffEntryIntent";

const STATUS_INTENT_STORAGE_KEY = "strayhub:volunteer-liff:status-intent";
const STATUS_INTENT_TTL_MS = 5 * 60 * 1000;
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type StoredStatusIntent = {
  view: "status";
  organizationId?: string;
  savedAt: number;
};

function hasExplicitApplicationView(query: string): boolean {
  const direct = new URLSearchParams(query);
  if (direct.get("view") === "application") return true;
  const state = direct.get("liff.state");
  if (!state || state.length > 2048 || !state.startsWith("?")) return false;
  return new URLSearchParams(state.slice(1)).get("view") === "application";
}

function readStoredStatusIntent(
  storage: Storage,
  now: number,
): VolunteerLiffEntryIntent | null {
  try {
    const raw = storage.getItem(STATUS_INTENT_STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<StoredStatusIntent>;
    if (
      value.view !== "status" ||
      typeof value.savedAt !== "number" ||
      now - value.savedAt > STATUS_INTENT_TTL_MS
    ) {
      storage.removeItem(STATUS_INTENT_STORAGE_KEY);
      return null;
    }
    const organizationId =
      typeof value.organizationId === "string" &&
      UUID_PATTERN.test(value.organizationId)
        ? value.organizationId
        : undefined;
    return {
      view: "status",
      ...(organizationId ? { organizationId } : {}),
      targetConflict: false,
    };
  } catch {
    storage.removeItem(STATUS_INTENT_STORAGE_KEY);
    return null;
  }
}

export function resolveVolunteerLiffLifecycleIntent(
  query: string,
  storage: Storage,
  now = Date.now(),
): VolunteerLiffEntryIntent {
  const parsed = parseVolunteerLiffEntryIntent(query);
  if (parsed.view === "status") return parsed;
  if (
    hasExplicitApplicationView(query) ||
    parsed.organizationId ||
    parsed.shelterEntryReference ||
    parsed.targetConflict
  ) {
    clearVolunteerLiffStatusIntent(storage);
    return parsed;
  }
  return readStoredStatusIntent(storage, now) ?? parsed;
}

export function persistVolunteerLiffStatusIntent(
  intent: VolunteerLiffEntryIntent,
  storage: Storage,
  now = Date.now(),
): void {
  if (intent.view !== "status") return;
  const organizationId =
    intent.organizationId && UUID_PATTERN.test(intent.organizationId)
      ? intent.organizationId
      : undefined;
  const value: StoredStatusIntent = {
    view: "status",
    ...(organizationId ? { organizationId } : {}),
    savedAt: now,
  };
  try {
    storage.setItem(STATUS_INTENT_STORAGE_KEY, JSON.stringify(value));
  } catch {
    // LIFF intent still remains in component state when storage is unavailable.
  }
}

export function clearVolunteerLiffStatusIntent(storage: Storage): void {
  try {
    storage.removeItem(STATUS_INTENT_STORAGE_KEY);
  } catch {
    // Storage availability must not block an explicit user transition.
  }
}

export function canonicalVolunteerLiffStatusQuery(
  intent: VolunteerLiffEntryIntent,
): string {
  const params = new URLSearchParams({ view: "status" });
  if (intent.organizationId && UUID_PATTERN.test(intent.organizationId)) {
    params.set("organization_id", intent.organizationId);
  }
  return params.toString();
}
