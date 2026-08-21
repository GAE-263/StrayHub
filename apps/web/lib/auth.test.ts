// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ACCESS_TOKEN_KEY,
  SESSION_SOURCE_KEY,
  authFetch,
  clearAuth,
  getSessionSource,
  storeSessionSource,
} from "./auth";
import { apiFetch } from "./api";
import {
  createRecoveryEpoch,
  getLiffEntryReference,
  getRecoveryEpoch,
  type OpaqueEntryReference,
  storeLiffEntryReference,
  storeRecoveryEpoch,
} from "./liff-session";

beforeEach(() => {
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
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

  it("preserves formal LIFF recovery state while clearing credentials", () => {
    window.sessionStorage.setItem(ACCESS_TOKEN_KEY, "access-token");
    storeSessionSource("liff");
    storeLiffEntryReference("opaque-entry-reference-0123456789abcdef");

    clearAuth({ preserveLiffSession: true });

    expect(window.sessionStorage.getItem(ACCESS_TOKEN_KEY)).toBeNull();
    expect(getSessionSource()).toBe("liff");
    expect(getLiffEntryReference()).toBe(
      "opaque-entry-reference-0123456789abcdef",
    );
  });

  it("restores formal LIFF recovery state after keyed cleanup fallback", () => {
    window.sessionStorage.setItem(ACCESS_TOKEN_KEY, "access-token");
    storeSessionSource("liff");
    storeLiffEntryReference("opaque-entry-reference-0123456789abcdef");
    const removeItem = vi
      .spyOn(window.sessionStorage, "removeItem")
      .mockImplementation((key: string) => {
        if (key === ACCESS_TOKEN_KEY) throw new Error("storage failure");
        Storage.prototype.removeItem.call(window.sessionStorage, key);
      });

    clearAuth({ preserveLiffSession: true });

    expect(getSessionSource()).toBe("liff");
    expect(getLiffEntryReference()).toBe(
      "opaque-entry-reference-0123456789abcdef",
    );
    removeItem.mockRestore();
  });

  it("publishes one recovery signal when an authenticated request returns 401", async () => {
    window.sessionStorage.setItem(ACCESS_TOKEN_KEY, "access-token");
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ status: 401, ok: false } as Response);
    vi.stubGlobal("fetch", fetchMock);
    const onUnauthorized = vi.fn();
    window.addEventListener("strayhub:liff-unauthorized", onUnauthorized);

    await authFetch("/v1/animals");

    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/animals",
      expect.objectContaining({
        headers: expect.any(Headers),
      }),
    );
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    window.removeEventListener("strayhub:liff-unauthorized", onUnauthorized);
  });

  it("defers LIFF recovery until a refresh attempt fails", async () => {
    window.sessionStorage.setItem(ACCESS_TOKEN_KEY, "access-token");
    window.sessionStorage.setItem("refresh_token", "refresh-token");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ status: 401, ok: false } as Response)
      .mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => ({
          access_token: "refreshed-access-token",
          refresh_token: "refreshed-refresh-token",
          session_id: "session-id",
        }),
      } as Response)
      .mockResolvedValueOnce({ status: 200, ok: true } as Response);
    vi.stubGlobal("fetch", fetchMock);
    const onUnauthorized = vi.fn();
    window.addEventListener("strayhub:liff-unauthorized", onUnauthorized);

    await apiFetch("/v1/animals");

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(onUnauthorized).not.toHaveBeenCalled();
    window.removeEventListener("strayhub:liff-unauthorized", onUnauthorized);
  });

  it("preserves LIFF recovery state until refresh failure signals recovery", async () => {
    window.sessionStorage.setItem(ACCESS_TOKEN_KEY, "access-token");
    window.sessionStorage.setItem("refresh_token", "refresh-token");
    storeSessionSource("liff");
    storeLiffEntryReference("opaque-entry-reference-0123456789abcdef");
    storeRecoveryEpoch({
      ...createRecoveryEpoch(1, "/animal-confirmation"),
      entryReference:
        "opaque-entry-reference-0123456789abcdef" as OpaqueEntryReference,
      exchangeAttempts: 1,
      state: "recovering",
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ status: 401, ok: false } as Response)
      .mockResolvedValueOnce({ status: 401, ok: false } as Response);
    vi.stubGlobal("fetch", fetchMock);
    const onUnauthorized = vi.fn();
    window.addEventListener("strayhub:liff-unauthorized", onUnauthorized);

    await apiFetch("/v1/animals");

    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    expect(getSessionSource()).toBe("liff");
    expect(getLiffEntryReference()).toBe(
      "opaque-entry-reference-0123456789abcdef",
    );
    expect(getRecoveryEpoch()?.state).toBe("recovering");
    window.removeEventListener("strayhub:liff-unauthorized", onUnauthorized);
  });

  it("single-flights concurrent refresh requests", async () => {
    window.sessionStorage.setItem(ACCESS_TOKEN_KEY, "access-token");
    window.sessionStorage.setItem("refresh_token", "refresh-token");
    let animalRequests = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (input === "/v1/auth/refresh") {
        return Promise.resolve({
          status: 200,
          ok: true,
          json: async () => ({
            access_token: "refreshed-access-token",
            refresh_token: "refreshed-refresh-token",
            session_id: "session-id",
          }),
        } as Response);
      }
      animalRequests += 1;
      return Promise.resolve(
        animalRequests <= 2
          ? ({ status: 401, ok: false } as Response)
          : ({ status: 200, ok: true } as Response),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    await Promise.all([apiFetch("/v1/animals"), apiFetch("/v1/animals")]);

    expect(
      fetchMock.mock.calls.filter(([input]) => input === "/v1/auth/refresh"),
    ).toHaveLength(1);
    expect(animalRequests).toBe(4);
  });

  it("discards a stale refresh response after the session changes", async () => {
    window.sessionStorage.setItem(ACCESS_TOKEN_KEY, "session-a-access-token");
    window.sessionStorage.setItem("refresh_token", "session-a-refresh-token");
    let resolveRefresh: ((value: Response) => void) | undefined;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (input === "/v1/auth/refresh") {
        return new Promise<Response>((resolve) => {
          resolveRefresh = resolve;
        });
      }
      return Promise.resolve({ status: 401, ok: false } as Response);
    });
    vi.stubGlobal("fetch", fetchMock);

    const pending = apiFetch("/v1/animals");
    await new Promise((resolve) => setTimeout(resolve, 0));
    window.sessionStorage.setItem("refresh_token", "session-b-refresh-token");
    resolveRefresh?.({
      status: 200,
      ok: true,
      json: async () => ({
        access_token: "stale-session-a-access-token",
        refresh_token: "stale-session-a-refresh-token",
        session_id: "session-a",
      }),
    } as Response);

    await pending;

    expect(window.sessionStorage.getItem(ACCESS_TOKEN_KEY)).toBe(
      "session-a-access-token",
    );
    expect(window.sessionStorage.getItem("refresh_token")).toBe(
      "session-b-refresh-token",
    );
  });

  it("does not replay a mutation after refreshing credentials", async () => {
    window.sessionStorage.setItem(ACCESS_TOKEN_KEY, "access-token");
    window.sessionStorage.setItem("refresh_token", "refresh-token");
    let animalRequests = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (input === "/v1/auth/refresh") {
        return Promise.resolve({
          status: 200,
          ok: true,
          json: async () => ({
            access_token: "refreshed-access-token",
            refresh_token: "refreshed-refresh-token",
            session_id: "session-id",
          }),
        } as Response);
      }
      animalRequests += 1;
      return Promise.resolve({ status: 401, ok: false } as Response);
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await apiFetch("/v1/animals", {
      method: "POST",
      body: JSON.stringify({ name: "animal" }),
    });

    expect(response.status).toBe(401);
    expect(animalRequests).toBe(1);
  });
});
