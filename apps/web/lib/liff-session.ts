export const LIFF_ENTRY_REFERENCE_KEY = "liff_entry_reference";
export const LIFF_RECOVERY_EPOCH_KEY = "liff_recovery_epoch";
const ENTRY_REFERENCE_PATTERN = /^[A-Za-z0-9_-]{32,512}$/;

export type LiffRecoveryState =
  "idle" | "recovering" | "exchanging" | "recovered" | "terminal";

export type LiffRecoveryEpoch = {
  epochId: number;
  exchangeAttempts: 0 | 1;
  entryReference: OpaqueEntryReference | null;
  originalPath: string;
  state: LiffRecoveryState;
};

export type LiffRecoveryStart =
  "started" | "in-flight" | "terminal" | "unavailable";

export type LiffRecoveryClaim = "claimed" | "in-flight" | "unavailable";

const RECOVERABLE_PATHS = new Set(["/animal-confirmation", "/care-report"]);

export type OpaqueEntryReference = string & {
  readonly __opaqueEntryReference: unique symbol;
};

export function isValidLiffEntryReference(
  reference: string,
): reference is OpaqueEntryReference {
  return ENTRY_REFERENCE_PATTERN.test(reference);
}

function getStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function isSafeOriginalPath(pathname: unknown): pathname is string {
  return (
    typeof pathname === "string" &&
    (RECOVERABLE_PATHS.has(pathname) ||
      /^\/assigned-care\/[A-Za-z0-9_-]+$/.test(pathname))
  );
}

export function storeLiffEntryReference(reference: string | null): void {
  const storage = getStorage();
  if (!storage) return;
  try {
    if (reference && isValidLiffEntryReference(reference)) {
      storage.setItem(LIFF_ENTRY_REFERENCE_KEY, reference);
    } else {
      storage.removeItem(LIFF_ENTRY_REFERENCE_KEY);
    }
  } catch {
    // Transient hints are optional; auth and route state fail closed elsewhere.
  }
}

export function getLiffEntryReference(): string | null {
  const storage = getStorage();
  if (!storage) return null;
  try {
    const reference = storage.getItem(LIFF_ENTRY_REFERENCE_KEY);
    return reference && isValidLiffEntryReference(reference) ? reference : null;
  } catch {
    return null;
  }
}

export function createRecoveryEpoch(
  epochId: number,
  originalPath: string,
): LiffRecoveryEpoch {
  return {
    epochId: Number.isSafeInteger(epochId) && epochId >= 0 ? epochId : 0,
    exchangeAttempts: 0,
    entryReference: null,
    originalPath: isSafeOriginalPath(originalPath)
      ? originalPath
      : "/animal-confirmation",
    state: "idle",
  };
}

export function storeRecoveryEpoch(epoch: LiffRecoveryEpoch): boolean {
  const storage = getStorage();
  if (!storage) return false;
  if (
    epoch.entryReference !== null &&
    !isValidLiffEntryReference(epoch.entryReference)
  ) {
    return false;
  }
  try {
    storage.setItem(LIFF_RECOVERY_EPOCH_KEY, JSON.stringify(epoch));
    return true;
  } catch {
    // Recovery metadata cannot grant access and is safe to discard.
    return false;
  }
}

function isRecoveryEpoch(value: unknown): value is LiffRecoveryEpoch {
  if (!value || typeof value !== "object") return false;
  const epoch = value as Partial<LiffRecoveryEpoch>;
  return (
    Number.isSafeInteger(epoch.epochId) &&
    (epoch.epochId as number) >= 0 &&
    (epoch.exchangeAttempts === 0 || epoch.exchangeAttempts === 1) &&
    (epoch.entryReference === null ||
      (typeof epoch.entryReference === "string" &&
        isValidLiffEntryReference(epoch.entryReference))) &&
    isSafeOriginalPath(epoch.originalPath) &&
    ["idle", "recovering", "exchanging", "recovered", "terminal"].includes(
      epoch.state ?? "",
    )
  );
}

export function getRecoveryEpoch(): LiffRecoveryEpoch | null {
  const storage = getStorage();
  if (!storage) return null;
  try {
    const raw = storage.getItem(LIFF_RECOVERY_EPOCH_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isRecoveryEpoch(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function beginLiffRecovery(originalPath: string): LiffRecoveryStart {
  const current = getRecoveryEpoch();
  if (current?.state === "recovering" || current?.state === "exchanging") {
    return "in-flight";
  }
  if (current?.state === "recovered" || current?.state === "terminal") {
    if (current.state === "recovered") {
      return storeRecoveryEpoch({ ...current, state: "terminal" })
        ? "terminal"
        : "unavailable";
    }
    return "terminal";
  }
  const entryReference = getLiffEntryReference();
  if (!entryReference) return "unavailable";
  const nextEpoch = {
    ...createRecoveryEpoch((current?.epochId ?? -1) + 1, originalPath),
    entryReference: entryReference as OpaqueEntryReference,
    exchangeAttempts: 1,
    state: "recovering",
  } satisfies LiffRecoveryEpoch;
  if (!storeRecoveryEpoch(nextEpoch)) return "unavailable";
  return "started";
}

export function claimLiffRecoveryExchange(): LiffRecoveryClaim {
  const current = getRecoveryEpoch();
  if (!current || current.state !== "recovering") {
    return current?.state === "exchanging" ? "in-flight" : "unavailable";
  }
  if (current.exchangeAttempts !== 1) return "unavailable";
  return storeRecoveryEpoch({ ...current, state: "exchanging" })
    ? "claimed"
    : "unavailable";
}

export function markLiffRecoveryRecovered(): boolean {
  const current = getRecoveryEpoch();
  if (current?.state === "recovering" || current?.state === "exchanging") {
    return storeRecoveryEpoch({ ...current, state: "recovered" });
  }
  return false;
}

export function markLiffRecoveryTerminal(): void {
  const current = getRecoveryEpoch();
  if (
    current?.state === "recovering" ||
    current?.state === "exchanging" ||
    current?.state === "recovered"
  ) {
    storeRecoveryEpoch({ ...current, state: "terminal" });
  }
}

export function resetLiffRecovery(): void {
  const storage = getStorage();
  if (!storage) return;
  try {
    storage.removeItem(LIFF_RECOVERY_EPOCH_KEY);
  } catch {
    // Recovery metadata is optional and never grants access.
  }
}

export function clearLiffSession(): void {
  const storage = getStorage();
  if (!storage) return;
  let removalFailed = false;
  for (const key of [LIFF_ENTRY_REFERENCE_KEY, LIFF_RECOVERY_EPOCH_KEY]) {
    try {
      storage.removeItem(key);
    } catch {
      removalFailed = true;
    }
  }
  if (removalFailed) {
    try {
      storage.clear();
    } catch {
      // Fail closed if browser storage is unavailable.
    }
  }
}
