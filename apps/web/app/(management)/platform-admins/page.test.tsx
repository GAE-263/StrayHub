// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

const routerReplace = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: routerReplace }),
}));

import PlatformAdminsPage from "./page";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

if (!HTMLDialogElement.prototype.showModal) {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value() {
      this.open = true;
    },
  });
}

if (!HTMLDialogElement.prototype.close) {
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value() {
      this.open = false;
    },
  });
}

const activeAdmin = {
  user_id: "admin-a",
  username: "local-platform-admin",
  display_name: "本機平台管理員",
  user_status: "active",
  platform_role: "PLATFORM_ADMIN",
  effective_status: "active",
  can_enable: false,
  can_disable: false,
  can_demote: false,
};

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

let root: Root | undefined;
let container: HTMLDivElement | undefined;

async function renderPage(listResponse?: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/auth/me")) {
        return response({
          user: {
            id: "admin-a",
            username: "local-platform-admin-disabled",
            display_name: "本機平台管理員",
            platform_role: "PLATFORM_ADMIN",
            status: "active",
          },
          memberships: [],
        });
      }
      if (path.endsWith("/candidates")) {
        return response([
          {
            user_id: "candidate-a",
            username: "local-staff-a",
            display_name: "本機工作人員 A",
          },
        ]);
      }
      if (path.endsWith("/platform/administrators")) {
        return response(
          listResponse ?? {
            policy: {
              min_active_admins: 1,
              max_active_admins: 2,
              active_count: 1,
              available_slots: 1,
            },
            items: [activeAdmin],
          },
        );
      }
      if (path.endsWith("/disable")) {
        return response({
          item: {
            ...activeAdmin,
            user_status: "disabled",
            effective_status: "disabled",
            can_disable: false,
          },
          policy: {
            min_active_admins: 1,
            max_active_admins: 2,
            active_count: 1,
            available_slots: 1,
          },
          operation_id: "operation-disable-self",
        });
      }
      if (path.includes("/platform/administrators/audit")) {
        return response([]);
      }
      return response({});
    }),
  );
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(<PlatformAdminsPage />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  container?.remove();
  container = undefined;
  routerReplace.mockReset();
  vi.unstubAllGlobals();
});

describe("platform administrator management page", () => {
  it("shows policy summary, identity and disabled-state sections", async () => {
    await renderPage();
    expect(container?.textContent).toContain("平台管理員");
    expect(container?.textContent).toContain("本機平台管理員");
    expect(container?.textContent).toContain("啟用中的平台管理員");
    expect(container?.textContent).toContain("已停用的平台管理員");
    expect(container?.textContent).toContain("剩餘名額");
    expect(container?.textContent).toContain("本機工作人員 A");
  });

  it("opens the create account modal", async () => {
    await renderPage();
    const button = Array.from(container?.querySelectorAll("button") ?? []).find(
      (candidate) => candidate.textContent?.trim() === "建立帳號",
    );
    await act(async () => button?.click());
    expect(container?.textContent).toContain("建立平台管理員帳號");
    expect(container?.querySelector('[role="dialog"]')).not.toBeNull();
  });

  it("opens the one-confirmation replacement modal", async () => {
    await renderPage();
    const button = Array.from(container?.querySelectorAll("button") ?? []).find(
      (candidate) => candidate.textContent?.trim() === "替換管理員",
    );
    await act(async () => button?.click());
    expect(container?.textContent).toContain("替換平台管理員");
    expect(container?.textContent).toContain("一次確認完成新舊權限交接");
  });

  it("renders demotion as an outlined button and keeps the promote action classed", async () => {
    await renderPage({
      policy: {
        min_active_admins: 1,
        max_active_admins: 2,
        active_count: 2,
        available_slots: 0,
      },
      items: [{ ...activeAdmin, can_demote: true }],
    });

    const demoteButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "降權");
    expect(demoteButton?.classList.contains("ui-button-secondary")).toBe(true);
    expect(
      container?.querySelector(".platform-admin-promote-submit"),
    ).not.toBeNull();
  });

  it("redirects instead of showing 401 when the current admin disables itself", async () => {
    await renderPage({
      policy: {
        min_active_admins: 1,
        max_active_admins: 2,
        active_count: 2,
        available_slots: 0,
      },
      items: [
        { ...activeAdmin, can_disable: true },
        {
          ...activeAdmin,
          user_id: "admin-b",
          username: "local-platform-admin-b",
          display_name: "本機平台管理員 B",
          can_disable: true,
        },
      ],
    });

    const disableButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "停用");
    await act(async () => disableButton?.click());

    expect(routerReplace).toHaveBeenCalledWith("/login");
    expect(container?.textContent).not.toContain("操作失敗：401: Session 無效");
  });
});
