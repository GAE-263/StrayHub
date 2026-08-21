// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { routerRef, replace, login, init, isLoggedIn, getIDToken } = vi.hoisted(
  () => {
    const replace = vi.fn();
    return {
      routerRef: { current: { replace } },
      replace,
      login: vi.fn(),
      init: vi.fn(),
      isLoggedIn: vi.fn(),
      getIDToken: vi.fn(),
    };
  },
);

vi.mock("next/navigation", () => ({
  useRouter: () => routerRef.current,
  useSearchParams: () =>
    React.useState(() => new URLSearchParams(window.location.search))[0],
}));
vi.mock("@line/liff", () => ({
  default: { init, login, isLoggedIn, getIDToken },
}));

import { scrubLegacyIdToken } from "./liffUrl";
import { getSessionSource } from "../../../lib/auth";
import {
  createRecoveryEpoch,
  getRecoveryEpoch,
  storeRecoveryEpoch,
} from "../../../lib/liff-session";
import type { OpaqueEntryReference } from "../../../lib/liff-session";
import VolunteerEntryPage from "./page";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | undefined;
let container: HTMLDivElement | undefined;

async function renderPage({ strict = false } = {}) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(
      strict ? (
        <React.StrictMode>
          <VolunteerEntryPage />
        </React.StrictMode>
      ) : (
        <VolunteerEntryPage />
      ),
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  return container;
}

beforeEach(() => {
  vi.stubEnv("LIFF_ID", "test-liff-id");
  vi.stubEnv("API_BASE_URL", "");
  window.history.replaceState({}, "", "/volunteer-entry?entry=entry-a");
  window.sessionStorage.clear();
  init.mockResolvedValue(undefined);
  isLoggedIn.mockReturnValue(true);
  getIDToken.mockReturnValue("raw-line-id-token");
  login.mockResolvedValue(undefined);
  replace.mockReset();
  routerRef.current = { replace };
});

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  container?.remove();
  container = undefined;
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe("volunteer entry LIFF bootstrap", () => {
  it("falls back to a token-free location replacement when history scrub fails", () => {
    const replaceLocation = vi.fn();
    const entryUrl = new URL(
      "https://example.test/volunteer-entry?entry=entry-a&id_token=legacy-secret",
    );

    expect(
      scrubLegacyIdToken(
        entryUrl,
        () => {
          throw new DOMException("history unavailable", "SecurityError");
        },
        replaceLocation,
      ),
    ).toBe(false);
    expect(replaceLocation).toHaveBeenCalledWith(
      "https://example.test/volunteer-entry?entry=entry-a",
    );
  });

  it("initializes LIFF and preserves the entry reference during login redirect", async () => {
    isLoggedIn.mockReturnValue(false);
    vi.stubGlobal("fetch", vi.fn());

    const view = await renderPage();

    expect(init).toHaveBeenCalledWith({ liffId: "test-liff-id" });
    expect(login).toHaveBeenCalledTimes(1);
    const redirectUri = login.mock.calls[0][0].redirectUri as string;
    expect(redirectUri).toContain("/volunteer-entry?entry=entry-a");
    expect(view.textContent).toContain("正在前往 LINE 登入");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("preserves the recovery exchange mode across a valid LIFF login redirect", async () => {
    const entry = "opaque-entry-reference-0123456789abcdef";
    window.history.replaceState({}, "", `/volunteer-entry?entry=${entry}`);
    isLoggedIn.mockReturnValue(false);
    vi.stubGlobal("fetch", vi.fn());

    await renderPage();

    expect(login).toHaveBeenCalledTimes(1);
    expect(login.mock.calls[0][0].redirectUri).toContain(
      `entry=${entry}&recovery=exchange`,
    );
    expect(getRecoveryEpoch()?.state).toBe("recovering");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("removes a legacy id token from the browser URL and login redirect", async () => {
    window.history.replaceState(
      {},
      "",
      "/volunteer-entry?entry=entry-a&id_token=legacy-secret-token",
    );
    isLoggedIn.mockReturnValue(false);
    vi.stubGlobal("fetch", vi.fn());

    await renderPage();

    expect(window.location.search).toBe("?entry=entry-a");
    const redirectUri = login.mock.calls[0][0].redirectUri as string;
    expect(redirectUri).toContain("?entry=entry-a");
    expect(redirectUri).not.toContain("id_token");
    expect(redirectUri).not.toContain("legacy-secret-token");
  });

  it("removes a legacy id token before stale auth cleanup can fail", async () => {
    window.history.replaceState(
      {},
      "",
      "/volunteer-entry?entry=entry-a&id_token=legacy-secret-token",
    );
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new DOMException("storage unavailable", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "clear").mockImplementation(() => {
      throw new DOMException("storage clear unavailable", "SecurityError");
    });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderPage();

    expect(window.location.search).toBe("?entry=entry-a");
    expect(window.location.href).not.toContain("legacy-secret-token");
    expect(view.textContent).toContain("無法清除舊的系統工作階段");
    expect(init).not.toHaveBeenCalled();
    expect(login).not.toHaveBeenCalled();
    expect(getIDToken).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
  });

  it("shows a safe LIFF initialization error without calling exchange", async () => {
    init.mockRejectedValue(new Error("secret LIFF initialization detail"));
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderPage();

    expect(view.textContent).toContain("目前無法連線確認志工資格");
    expect(view.textContent).not.toContain("secret LIFF initialization detail");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(view.querySelector("button")?.textContent).toContain("重新嘗試");
    expect(view.querySelector("main")?.classList).toContain(
      "volunteer-entry-error",
    );
    expect(view.querySelector(".volunteer-entry-content")).not.toBeNull();
  });

  it("stores the internal session before replacing to animal confirmation", async () => {
    replace.mockImplementation(() => {
      expect(window.sessionStorage.getItem("access_token")).toBe(
        "internal-access-token",
      );
      expect(window.sessionStorage.getItem("session_id")).toBe("session-a");
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          state: "ACTIVE",
          access_token: "internal-access-token",
          refresh_token: "internal-refresh-token",
          session_id: "session-a",
          organization: { id: "org-a", code: "ORG-A", name: "收容所 A" },
          user: { role: "VOLUNTEER" },
          next_path: "/animal-confirmation",
        }),
      }),
    );

    await renderPage();

    expect(fetch).toHaveBeenCalledWith(
      "/v1/auth/liff/exchange",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          id_token: "raw-line-id-token",
          shelter_entry_reference: "entry-a",
        }),
      }),
    );
    expect(getSessionSource()).toBe("liff");
    expect(replace).toHaveBeenCalledWith("/animal-confirmation");
  });

  it("keeps automatic recovery alive across React StrictMode effect replay", async () => {
    const entry = "opaque-entry-reference-0123456789abcdef";
    window.history.replaceState(
      {},
      "",
      `/volunteer-entry?entry=${entry}&recovery=exchange`,
    );
    storeRecoveryEpoch({
      ...createRecoveryEpoch(1, "/animal-confirmation"),
      entryReference: entry as OpaqueEntryReference,
      exchangeAttempts: 1,
      state: "recovering",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          state: "ACTIVE",
          access_token: "internal-access-token",
          refresh_token: "internal-refresh-token",
          session_id: "session-a",
          organization: { id: "org-a", code: "ORG-A", name: "收容所 A" },
          user: { role: "VOLUNTEER" },
          next_path: "/animal-confirmation",
        }),
      }),
    );

    await renderPage({ strict: true });

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalledWith("/animal-confirmation");
  });

  it("adopts a fresh recovery epoch across React StrictMode effect replay", async () => {
    const entry = "opaque-entry-reference-0123456789abcdef";
    window.history.replaceState({}, "", `/volunteer-entry?entry=${entry}`);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          state: "ACTIVE",
          access_token: "internal-access-token",
          refresh_token: "internal-refresh-token",
          session_id: "session-a",
          organization: { id: "org-a", code: "ORG-A", name: "收容所 A" },
          user: { role: "VOLUNTEER" },
          next_path: "/animal-confirmation",
        }),
      }),
    );

    await renderPage({ strict: true });

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(getRecoveryEpoch()?.state).toBe("recovered");
    expect(replace).toHaveBeenCalledWith("/animal-confirmation");
  });

  it("cancels a claimed recovery exchange when the entry page unmounts", async () => {
    const entry = "opaque-entry-reference-0123456789abcdef";
    window.history.replaceState(
      {},
      "",
      `/volunteer-entry?entry=${entry}&recovery=exchange`,
    );
    storeRecoveryEpoch({
      ...createRecoveryEpoch(1, "/animal-confirmation"),
      entryReference: entry as OpaqueEntryReference,
      exchangeAttempts: 1,
      state: "recovering",
    });
    let firstSignal: AbortSignal | undefined;
    let resolveFirstFetch:
      ((value: { ok: true; json: () => Promise<unknown> }) => void) | undefined;
    const successfulExchange = {
      ok: true as const,
      json: async () => ({
        state: "ACTIVE",
        access_token: "internal-access-token",
        refresh_token: "internal-refresh-token",
        session_id: "session-a",
        organization: { id: "org-a", code: "ORG-A", name: "收容所 A" },
        user: { role: "VOLUNTEER" },
      }),
    };
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementationOnce((_url, options: RequestInit) => {
          firstSignal = options.signal ?? undefined;
          return new Promise((resolve) => {
            resolveFirstFetch = resolve;
          });
        })
        .mockResolvedValueOnce(successfulExchange),
    );

    await renderPage();
    expect(getRecoveryEpoch()?.state).toBe("exchanging");

    await act(async () => {
      window.history.replaceState(
        {},
        "",
        "/volunteer-entry?entry=opaque-entry-reference-fedcba9876543210&recovery=exchange",
      );
      root?.unmount();
      await Promise.resolve();
    });
    expect(firstSignal?.aborted).toBe(true);
    expect(getRecoveryEpoch()).toBeNull();
    resolveFirstFetch?.(successfulExchange);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    await renderPage();
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(fetch).toHaveBeenCalledTimes(2);
    expect(getRecoveryEpoch()?.state).toBe("recovered");
    expect(replace).toHaveBeenCalledWith("/animal-confirmation");
  });

  it("allows manual retry to replace a stale exchanging epoch after reload", async () => {
    const entry = "opaque-entry-reference-0123456789abcdef";
    window.history.replaceState(
      {},
      "",
      `/volunteer-entry?entry=${entry}&recovery=exchange`,
    );
    storeRecoveryEpoch({
      ...createRecoveryEpoch(1, "/animal-confirmation"),
      entryReference: entry as OpaqueEntryReference,
      exchangeAttempts: 1,
      state: "exchanging",
    });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        state: "PENDING",
        organization: { id: "org-a", code: "ORG-A", name: "收容所 A" },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderPage();
    expect(fetchMock).not.toHaveBeenCalled();

    await act(async () => {
      view
        .querySelector("button")
        ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(view.textContent).toContain("志工申請審核中");
  });

  it("ignores an untrusted ACTIVE next path", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          state: "ACTIVE",
          access_token: "internal-access-token",
          refresh_token: "internal-refresh-token",
          session_id: "session-a",
          organization: { id: "org-a", code: "ORG-A", name: "收容所 A" },
          user: { role: "VOLUNTEER" },
          next_path: "https://attacker.invalid/credential-handoff",
        }),
      }),
    );

    await renderPage();

    expect(replace).toHaveBeenCalledWith("/animal-confirmation");
    expect(replace).not.toHaveBeenCalledWith(
      "https://attacker.invalid/credential-handoff",
    );
  });

  it("clears an old session when ACTIVE is missing a refresh token", async () => {
    window.sessionStorage.setItem("access_token", "old-access-token");
    window.sessionStorage.setItem("refresh_token", "old-refresh-token");
    window.sessionStorage.setItem("session_id", "old-session-id");
    window.sessionStorage.setItem("active_organization_id", "old-org");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          state: "ACTIVE",
          access_token: "new-access-token",
          session_id: "new-session-id",
          organization: { id: "org-a", code: "ORG-A", name: "收容所 A" },
          user: { role: "VOLUNTEER" },
        }),
      }),
    );

    const view = await renderPage();

    expect(view.textContent).toContain("系統工作階段建立失敗");
    expect(replace).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem("access_token")).toBeNull();
    expect(window.sessionStorage.getItem("refresh_token")).toBeNull();
    expect(window.sessionStorage.getItem("session_id")).toBeNull();
    expect(window.sessionStorage.getItem("active_organization_id")).toBeNull();
  });

  it.each([
    ["access token", { access_token: " " }],
    ["refresh token", { refresh_token: " " }],
    ["session id", { session_id: " " }],
    [
      "organization id",
      { organization: { id: " ", code: "ORG-A", name: "收容所 A" } },
    ],
    [
      "organization code",
      { organization: { id: "org-a", code: " ", name: "收容所 A" } },
    ],
    [
      "organization name",
      { organization: { id: "org-a", code: "ORG-A", name: " " } },
    ],
    ["volunteer role", { user: { role: "SHELTER_ADMIN" } }],
  ])("rejects ACTIVE with an invalid %s", async (_field, override) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          state: "ACTIVE",
          access_token: "internal-access-token",
          refresh_token: "internal-refresh-token",
          session_id: "session-a",
          organization: { id: "org-a", code: "ORG-A", name: "收容所 A" },
          user: { role: "VOLUNTEER" },
          ...override,
        }),
      }),
    );

    const view = await renderPage();

    expect(view.textContent).toContain("系統工作階段建立失敗");
    expect(window.sessionStorage.getItem("access_token")).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });

  it("does not redirect when the internal session cannot be stored", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("secret storage detail");
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          state: "ACTIVE",
          access_token: "internal-access-token",
          refresh_token: "internal-refresh-token",
          session_id: "session-a",
          organization: { id: "org-a", code: "ORG-A", name: "收容所 A" },
          user: { role: "VOLUNTEER" },
          next_path: "/animal-confirmation",
        }),
      }),
    );

    const view = await renderPage();

    expect(view.textContent).toContain("無法保存系統工作階段");
    expect(view.textContent).not.toContain("secret storage detail");
    expect(replace).not.toHaveBeenCalled();
  });

  it("clears partial credentials when active organization storage fails", async () => {
    const setItem = Storage.prototype.setItem;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
      this: Storage,
      key,
      value,
    ) {
      if (key === "active_organization_id") {
        throw new Error("secret organization storage detail");
      }
      setItem.call(this, key, value);
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          state: "ACTIVE",
          access_token: "internal-access-token",
          refresh_token: "internal-refresh-token",
          session_id: "session-a",
          organization: { id: "org-a", code: "ORG-A", name: "收容所 A" },
          user: { role: "VOLUNTEER" },
          next_path: "/animal-confirmation",
        }),
      }),
    );

    const view = await renderPage();

    expect(view.textContent).toContain("無法保存系統工作階段");
    expect(replace).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem("access_token")).toBeNull();
    expect(window.sessionStorage.getItem("refresh_token")).toBeNull();
    expect(window.sessionStorage.getItem("session_id")).toBeNull();
    expect(window.sessionStorage.getItem("active_organization_id")).toBeNull();
    expect(
      window.sessionStorage.getItem("active_organization_code"),
    ).toBeNull();
  });

  it("clears partial credentials when one keyed removal also fails", async () => {
    const setItem = Storage.prototype.setItem;
    const removeItem = Storage.prototype.removeItem;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
      this: Storage,
      key,
      value,
    ) {
      if (key === "active_organization_id") {
        throw new DOMException("write unavailable", "SecurityError");
      }
      setItem.call(this, key, value);
    });
    let accessRemovalCount = 0;
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(function (
      this: Storage,
      key,
    ) {
      if (key === "access_token" && ++accessRemovalCount > 1) {
        throw new DOMException("remove unavailable", "SecurityError");
      }
      removeItem.call(this, key);
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          state: "ACTIVE",
          access_token: "internal-access-token",
          refresh_token: "internal-refresh-token",
          session_id: "session-a",
          organization: { id: "org-a", code: "ORG-A", name: "收容所 A" },
          user: { role: "VOLUNTEER" },
        }),
      }),
    );

    const view = await renderPage();

    expect(view.textContent).toContain("無法保存系統工作階段");
    expect(replace).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem("access_token")).toBeNull();
    expect(window.sessionStorage.getItem("refresh_token")).toBeNull();
    expect(window.sessionStorage.getItem("session_id")).toBeNull();
    expect(window.sessionStorage.getItem("active_organization_id")).toBeNull();
    expect(
      window.sessionStorage.getItem("active_organization_code"),
    ).toBeNull();
  });

  it.each([
    ["NEW", "尚未完成志工報名"],
    ["PENDING", "志工申請審核中"],
    ["SUSPENDED", "目前無法使用志工服務"],
  ])(
    "renders the %s onboarding state without issuing a session",
    async (state, copy) => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({
            state,
            organization: { id: "org-a", code: "ORG-A", name: "收容所 A" },
          }),
        }),
      );

      const view = await renderPage();

      expect(view.textContent).toContain(copy);
      expect(window.sessionStorage.getItem("access_token")).toBeNull();
      expect(replace).not.toHaveBeenCalled();
    },
  );

  it.each([
    [
      "NEW",
      () =>
        Promise.resolve({
          ok: true,
          json: async () => ({ state: "NEW" }),
        }),
    ],
    [
      "PENDING",
      () =>
        Promise.resolve({
          ok: true,
          json: async () => ({ state: "PENDING" }),
        }),
    ],
    [
      "SUSPENDED",
      () =>
        Promise.resolve({
          ok: true,
          json: async () => ({ state: "SUSPENDED" }),
        }),
    ],
    [
      "401",
      () =>
        Promise.resolve({
          ok: false,
          status: 401,
          json: async () => ({ code: "invalid_line_id_token" }),
        }),
    ],
    [
      "403",
      () =>
        Promise.resolve({
          ok: false,
          status: 403,
          json: async () => ({ code: "entry_unavailable" }),
        }),
    ],
    [
      "503",
      () =>
        Promise.resolve({
          ok: false,
          status: 503,
          json: async () => ({ code: "liff_exchange_unavailable" }),
        }),
    ],
    [
      "unknown state",
      () =>
        Promise.resolve({
          ok: true,
          json: async () => ({ state: "UNEXPECTED_STATE" }),
        }),
    ],
    ["network failure", () => Promise.reject(new Error("network detail"))],
  ])("clears stale auth before a %s result", async (_result, exchange) => {
    const staleAuth = {
      access_token: "old-access-token",
      refresh_token: "old-refresh-token",
      session_id: "old-session-id",
      active_organization_id: "old-org",
      active_organization_code: "OLD",
    };
    for (const [key, value] of Object.entries(staleAuth)) {
      window.sessionStorage.setItem(key, value);
    }
    vi.stubGlobal("fetch", vi.fn().mockImplementation(exchange));

    await renderPage();

    for (const key of Object.keys(staleAuth)) {
      expect(window.sessionStorage.getItem(key)).toBeNull();
    }
    expect(replace).not.toHaveBeenCalled();
  });

  it("hands NEW off to application submission and renders PENDING", async () => {
    const organization = {
      id: "org-a",
      code: "ORG-A",
      name: "收容所 A",
      applications_enabled: true,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ state: "NEW", organization }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          organization,
          application: null,
          grant: null,
          effective_status: "none",
          next_actions: ["apply"],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          organization,
          application: {
            id: "application-a",
            status: "pending",
            version: 1,
          },
          grant: null,
          effective_status: "pending",
          next_actions: ["withdraw"],
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderPage();
    const buttonNamed = (name: string) =>
      [...view.querySelectorAll("button")].find((button) =>
        button.textContent?.includes(name),
      );

    await act(async () => {
      buttonNamed("進入志工報名")?.dispatchEvent(
        new MouseEvent("click", { bubbles: true }),
      );
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(view.textContent).toContain("成為志工");

    await act(async () => {
      view
        .querySelector<HTMLInputElement>('input[type="checkbox"]')
        ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await act(async () => {
      buttonNamed("立即報名")?.dispatchEvent(
        new MouseEvent("click", { bubbles: true }),
      );
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(view.textContent).toContain("等待收容所審核");
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const statusCall = fetchMock.mock.calls.find(
      ([url]) => url === "/v1/volunteer-applications/status",
    );
    const submitCall = fetchMock.mock.calls.find(
      ([url]) => url === "/v1/volunteer-applications",
    );
    const statusBody = JSON.parse(statusCall?.[1]?.body as string) as {
      id_token?: string;
      shelter_entry_reference?: string;
    };
    const submitBody = JSON.parse(submitCall?.[1]?.body as string) as {
      client_request_id?: string;
      consent_acknowledged?: boolean;
      id_token?: string;
      shelter_entry_reference?: string;
    };
    expect(statusBody).toEqual({
      id_token: "raw-line-id-token",
      shelter_entry_reference: "entry-a",
    });
    expect(submitBody).toEqual(
      expect.objectContaining({
        consent_acknowledged: true,
        id_token: "raw-line-id-token",
        shelter_entry_reference: "entry-a",
      }),
    );
    expect(submitBody.client_request_id).toEqual(expect.any(String));
    expect(window.location.search).toBe("?entry=entry-a");
    expect(window.location.href).not.toContain("raw-line-id-token");
  });

  it("shows a safe missing-token error and allows a manual retry", async () => {
    getIDToken.mockReturnValue(null);
    vi.stubGlobal("fetch", vi.fn());

    const view = await renderPage();

    expect(view.textContent).toContain("無法取得 LINE 身分資訊");
    expect(view.textContent).not.toContain("raw-line-id-token");
    expect(fetch).not.toHaveBeenCalled();
    expect(view.querySelector("button")?.textContent).toContain("重新嘗試");
  });

  it("shows a safe network error without automatic retry", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValue(new Error("secret network detail"));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderPage();

    expect(view.textContent).toContain("目前無法連線確認志工資格");
    expect(view.textContent).not.toContain("secret network detail");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows a safe dependency error without exposing the server detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({
          code: "liff_exchange_unavailable",
          message: "secret database detail",
        }),
      }),
    );

    const view = await renderPage();

    expect(view.textContent).toContain("志工服務暫時無法使用");
    expect(view.textContent).not.toContain("secret database detail");
    expect(window.sessionStorage.getItem("access_token")).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });

  it("fails closed when a successful exchange returns an unknown state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          state: "UNEXPECTED_STATE",
          access_token: "must-not-be-stored",
          session_id: "must-not-be-stored",
          organization: { id: "org-a", code: "ORG-A", name: "收容所 A" },
          user: { role: "VOLUNTEER" },
        }),
      }),
    );

    const view = await renderPage();

    expect(view.textContent).toContain("無法確認志工資格");
    expect(window.sessionStorage.getItem("access_token")).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });

  it("retries exchange only after the user presses retry", async () => {
    window.history.replaceState(
      {},
      "",
      "/volunteer-entry?entry=opaque-entry-reference-0123456789abcdef",
    );
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error("temporary network detail"))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          state: "PENDING",
          organization: { id: "org-a", code: "ORG-A", name: "收容所 A" },
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderPage();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      view
        .querySelector("button")
        ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      view
        .querySelector("button")
        ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(view.textContent).toContain("志工申請審核中");
    expect(replace).not.toHaveBeenCalled();
  });

  it("marks a failed recovery URL terminal before a reload can retry it", async () => {
    window.history.replaceState(
      {},
      "",
      "/volunteer-entry?entry=opaque-entry-reference-0123456789abcdef&recovery=exchange",
    );
    storeRecoveryEpoch({
      ...createRecoveryEpoch(1, "/animal-confirmation"),
      entryReference:
        "opaque-entry-reference-0123456789abcdef" as OpaqueEntryReference,
      exchangeAttempts: 1,
      state: "recovering",
    });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network")));

    await renderPage();

    expect(new URL(window.location.href).searchParams.get("recovery")).toBe(
      "terminal",
    );
  });

  it("honors a terminal URL marker even when persisted state is recovered", async () => {
    const entry = "opaque-entry-reference-0123456789abcdef";
    window.history.replaceState(
      {},
      "",
      `/volunteer-entry?entry=${entry}&recovery=terminal`,
    );
    storeRecoveryEpoch({
      ...createRecoveryEpoch(1, "/animal-confirmation"),
      entryReference: entry as OpaqueEntryReference,
      exchangeAttempts: 1,
      state: "recovered",
    });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderPage();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(view.textContent).toContain("系統工作階段已失效");
  });

  it("ignores an older failed exchange after a newer bootstrap succeeds", async () => {
    let resolveOldBody: ((value: { code: string }) => void) | undefined;
    const oldBody = new Promise<{ code: string }>((resolve) => {
      resolveOldBody = resolve;
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: () => oldBody,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          state: "NEW",
          organization: { id: "org-a", code: "ORG-A", name: "收容所 A" },
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderPage();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    routerRef.current = { replace };
    await act(async () => {
      root?.render(<VolunteerEntryPage />);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(view.textContent).toContain("尚未完成志工報名");

    await act(async () => {
      resolveOldBody?.({ code: "liff_exchange_unavailable" });
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(view.textContent).toContain("尚未完成志工報名");
    expect(view.textContent).not.toContain("志工服務暫時無法使用");
  });
});
