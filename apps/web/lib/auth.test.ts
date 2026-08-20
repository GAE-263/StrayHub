// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";

import {
  ACCESS_TOKEN_KEY,
  SESSION_SOURCE_KEY,
  clearAuth,
  getSessionSource,
  storeSessionSource,
} from "./auth";
import { getLiffEntryReference, storeLiffEntryReference } from "./liff-session";

beforeEach(() => {
  window.sessionStorage.clear();
});

describe("authenticated session source", () => {
  it.each(["local", "liff"] as const)("stores a typed %s source", (source) => {
    storeSessionSource(source);
    expect(getSessionSource()).toBe(source);
  });

  it("rejects an unknown stored source", () => {
    window.sessionStorage.setItem(SESSION_SOURCE_KEY, "client-cache");
    expect(getSessionSource()).toBeNull();
  });

  it("removes the source with auth terminal cleanup", () => {
    window.sessionStorage.setItem(ACCESS_TOKEN_KEY, "access-token");
    storeSessionSource("liff");
    storeLiffEntryReference("opaque-entry-reference-0123456789abcdef");

    clearAuth();

    expect(window.sessionStorage.getItem(ACCESS_TOKEN_KEY)).toBeNull();
    expect(getSessionSource()).toBeNull();
    expect(getLiffEntryReference()).toBeNull();
  });
});
