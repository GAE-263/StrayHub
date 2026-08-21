export type RecoveryOwnerClaim = {
  owner: symbol;
  entryReference: string;
  epochId: number;
  controller: AbortController | null;
  claimedAt: number;
};

export type RecoveryOwnerClaimResult = "started" | "same-owner" | "replaced";

let activeClaim: RecoveryOwnerClaim | null = null;

export function claimRecoveryOwner(
  owner: symbol,
  entryReference: string,
  epochId: number,
): RecoveryOwnerClaimResult {
  if (
    activeClaim &&
    activeClaim.owner === owner &&
    activeClaim.entryReference === entryReference &&
    activeClaim.epochId === epochId
  ) {
    return "same-owner";
  }

  const hadPreviousClaim = activeClaim !== null;
  activeClaim?.controller?.abort();
  activeClaim = {
    owner,
    entryReference,
    epochId,
    controller: null,
    claimedAt: Date.now(),
  };
  return hadPreviousClaim ? "replaced" : "started";
}

export function getRecoveryOwnerClaim(): RecoveryOwnerClaim | null {
  return activeClaim;
}

export function isRecoveryOwnerCurrent(
  owner: symbol,
  entryReference: string,
  epochId: number | null,
): boolean {
  return (
    activeClaim !== null &&
    activeClaim.owner === owner &&
    activeClaim.entryReference === entryReference &&
    activeClaim.epochId === epochId
  );
}

export function setRecoveryOwnerController(
  owner: symbol,
  entryReference: string,
  epochId: number,
  controller: AbortController,
): boolean {
  if (
    !activeClaim ||
    activeClaim.owner !== owner ||
    activeClaim.entryReference !== entryReference ||
    activeClaim.epochId !== epochId
  ) {
    return false;
  }
  activeClaim = { ...activeClaim, controller, claimedAt: Date.now() };
  return true;
}

export function releaseRecoveryOwner(
  owner: symbol,
  entryReference: string,
  epochId: number | null,
  abort = false,
): boolean {
  if (
    !activeClaim ||
    activeClaim.owner !== owner ||
    activeClaim.entryReference !== entryReference ||
    activeClaim.epochId !== epochId
  ) {
    return false;
  }
  if (abort) activeClaim.controller?.abort();
  activeClaim = null;
  return true;
}

export function resetRecoveryOwnerClaims(): void {
  activeClaim?.controller?.abort();
  activeClaim = null;
}
