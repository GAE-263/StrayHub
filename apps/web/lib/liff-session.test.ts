// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearLiffSession,
  createRecoveryEpoch,
  getLiffEntryReference,
  getRecoveryEpoch,
  storeLiffEntryReference,
  storeRecoveryEpoch,
} from "./liff-session";

beforeEach(() => {
  window.sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("LIFF transient session state", () => {
  it("stores and reads an opaque entry reference without decoding it", () => {
    const reference = "opaque-entry-reference-0123456789abcdef";
    storeLiffEntryReference(reference);

    expect(getLiffEntryReference()).toBe(reference);
    expect(window.sessionStorage.getItem("liff_entry_reference")).toBe(
      reference,
    );
  });

  it("rejects blank entry references and clears transient state", () => {
    storeLiffEntryReference(" ");
    expect(getLiffEntryReference()).toBeNull();

    storeLiffEntryReference("entry-a");
    clearLiffSession();
    expect(getLiffEntryReference()).toBeNull();
    expect(getRecoveryEpoch()).toBeNull();
  });

  it("creates a bounded recovery epoch with one exchange attempt", () => {
    const epoch = createRecoveryEpoch(3, "/animal-confirmation");
    storeRecoveryEpoch(epoch);

    expect(getRecoveryEpoch()).toEqual({
      epochId: 3,
      exchangeAttempts: 0,
      entryReference: null,
      originalPath: "/animal-confirmation",
      state: "idle",
    });
  });

  it("rejects unsafe recovery paths and malformed entry references", () => {
    expect(createRecoveryEpoch(3, "/assigned-care/").originalPath).toBe(
      "/animal-confirmation",
    );
    expect(
      createRecoveryEpoch(3, "/assigned-care/%2e%2e/settings").originalPath,
    ).toBe("/animal-confirmation");

    storeLiffEntryReference("too-short");
    expect(getLiffEntryReference()).toBeNull();
  });

  it("fails closed when stored recovery metadata is malformed", () => {
    window.sessionStorage.setItem(
      "liff_recovery_epoch",
      JSON.stringify({ epochId: "not-a-number", state: "recovering" }),
    );

    expect(getRecoveryEpoch()).toBeNull();
  });

  it("does not throw when transient storage is unavailable", () => {
    vi.spyOn(window.sessionStorage, "setItem").mockImplementation(() => {
      throw new Error("storage unavailable");
    });
    vi.spyOn(window.sessionStorage, "getItem").mockImplementation(() => {
      throw new Error("storage unavailable");
    });

    expect(() => storeLiffEntryReference("entry-a")).not.toThrow();
  });
});
