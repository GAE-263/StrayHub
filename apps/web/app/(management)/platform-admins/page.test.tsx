// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
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

async function renderPage() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
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
        return response({
          policy: {
            min_active_admins: 1,
            max_active_admins: 2,
            active_count: 1,
            available_slots: 1,
          },
          items: [activeAdmin],
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
});
