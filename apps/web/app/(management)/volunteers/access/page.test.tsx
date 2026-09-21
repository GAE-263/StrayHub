// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
}));

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

function response(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response;
}

async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

let root: Root | undefined;
let container: HTMLDivElement | undefined;

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function showModal() {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close() {
    this.open = false;
  };
});

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  container?.remove();
  container = undefined;
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
});

const grantFixture = {
  id: "grant-a",
  user_id: "user-a",
  membership_id: "membership-a",
  display_name: "測試志工",
  status: "active",
  valid_from: "2026-08-15T04:00:00Z",
  expires_at: "2026-08-22T04:00:00Z",
  version: 1,
  source_type: "manager_approval",
};

describe("VolunteerAccessPage", () => {
  it("gates PLATFORM_ADMIN behind a support reason and attaches it to load/mutate requests", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input), "http://localhost");
        if (url.pathname.endsWith("/v1/auth/me"))
          return response({ user: { platform_role: "PLATFORM_ADMIN" } });
        const headers = new Headers(init?.headers);
        const supportReason = headers.get("X-Platform-Support-Reason");
        if (!supportReason) {
          return {
            ok: false,
            status: 422,
            json: async () => ({ code: "platform_support_reason_required" }),
          } as Response;
        }
        expect(supportReason).toBe(encodeURIComponent("跨收容所支援審核"));
        if (init?.method === "PATCH") {
          return response({ ...grantFixture, status: "revoked", version: 2 });
        }
        return response({ items: [grantFixture] });
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("React", React);
    window.sessionStorage.setItem("access_token", "local-token");
    window.sessionStorage.setItem("active_organization_id", "org-a");

    const { default: VolunteerAccessPage } = await import("./page");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(<VolunteerAccessPage />);
      await flush();
    });

    expect(container.textContent).toContain("平台支援原因");
    expect(container.textContent).not.toContain("測試志工");

    const reasonInput = container.querySelector(
      "#platform-support-reason",
    ) as HTMLInputElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )?.set?.call(reasonInput, "跨收容所支援審核");
      reasonInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container
        ?.querySelector("form")
        ?.dispatchEvent(
          new Event("submit", { bubbles: true, cancelable: true }),
        );
      await flush();
    });

    expect(container.textContent).toContain("測試志工");

    const revokeButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("撤銷授權"),
    );
    const reasonField = container.querySelector(
      'input[aria-label="測試志工 操作原因"]',
    ) as HTMLInputElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )?.set?.call(reasonField, "測試撤銷");
      reasonField.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => revokeButton?.click());
    const confirmButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("確認調整"),
    );
    await act(async () => {
      confirmButton?.click();
      await flush();
    });

    const patchCall = fetchMock.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "PATCH",
    );
    expect(patchCall).toBeDefined();
    const patchHeaders = new Headers(
      (patchCall?.[1] as RequestInit | undefined)?.headers,
    );
    expect(patchHeaders.get("X-Platform-Support-Reason")).toBe(
      encodeURIComponent("跨收容所支援審核"),
    );
  });

  it("loads directly for SHELTER_ADMIN without a support reason gate", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname.endsWith("/v1/auth/me"))
        return response({ user: { platform_role: null } });
      return response({ items: [grantFixture] });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("React", React);
    window.sessionStorage.setItem("access_token", "local-token");
    window.sessionStorage.setItem("active_organization_id", "org-a");

    const { default: VolunteerAccessPage } = await import("./page");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(<VolunteerAccessPage />);
      await flush();
    });

    expect(container.textContent).not.toContain("平台支援原因");
    expect(container.textContent).toContain("測試志工");
  });
});
