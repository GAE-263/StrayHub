import { beforeEach, describe, expect, it } from "vitest";

import {
  claimRecoveryOwner,
  getRecoveryOwnerClaim,
  isRecoveryOwnerCurrent,
  releaseRecoveryOwner,
  resetRecoveryOwnerClaims,
  setRecoveryOwnerController,
} from "./liff-recovery-coordinator";

const entryA = "opaque-entry-reference-0123456789abcdef";
const entryB = "opaque-entry-reference-fedcba9876543210";

beforeEach(() => {
  resetRecoveryOwnerClaims();
});

describe("LIFF recovery owner coordination", () => {
  it("allows StrictMode re-entry for the same owner and entry", () => {
    const owner = Symbol("entry-a");

    expect(claimRecoveryOwner(owner, entryA, 1)).toBe("started");
    expect(claimRecoveryOwner(owner, entryA, 1)).toBe("same-owner");
    expect(getRecoveryOwnerClaim()).toMatchObject({
      owner,
      entryReference: entryA,
      epochId: 1,
    });
  });

  it("aborts and replaces an in-flight claim for a different owner or entry", () => {
    const ownerA = Symbol("entry-a");
    const ownerB = Symbol("entry-b");
    const controller = new AbortController();

    claimRecoveryOwner(ownerA, entryA, 1);
    setRecoveryOwnerController(ownerA, entryA, 1, controller);

    expect(claimRecoveryOwner(ownerB, entryB, 2)).toBe("replaced");
    expect(controller.signal.aborted).toBe(true);
    expect(getRecoveryOwnerClaim()).toMatchObject({
      owner: ownerB,
      entryReference: entryB,
      epochId: 2,
    });
  });

  it("does not let an old owner release a replacement claim", () => {
    const ownerA = Symbol("entry-a");
    const ownerB = Symbol("entry-b");

    claimRecoveryOwner(ownerA, entryA, 1);
    claimRecoveryOwner(ownerB, entryB, 2);

    expect(releaseRecoveryOwner(ownerA, entryA, 1)).toBe(false);
    expect(getRecoveryOwnerClaim()).toMatchObject({
      owner: ownerB,
      entryReference: entryB,
      epochId: 2,
    });
    expect(releaseRecoveryOwner(ownerB, entryB, 2)).toBe(true);
    expect(getRecoveryOwnerClaim()).toBeNull();
  });

  it("rejects a late response from an owner replaced by another entry", () => {
    const ownerA = Symbol("entry-a");
    const ownerB = Symbol("entry-b");

    claimRecoveryOwner(ownerA, entryA, 0);
    claimRecoveryOwner(ownerB, entryB, 0);

    expect(isRecoveryOwnerCurrent(ownerA, entryA, 0)).toBe(false);
    expect(isRecoveryOwnerCurrent(ownerB, entryB, 0)).toBe(true);
  });
});
