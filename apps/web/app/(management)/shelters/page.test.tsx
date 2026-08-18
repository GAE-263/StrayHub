// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import SheltersManagementPage from "./page";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const organization = {
  id: "org-a",
  code: "ORG-A",
  name: "浪浪森友會 A",
  status: "active",
  timezone: "Asia/Taipei",
  timezone_version: 1,
};

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

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function mockFetch(role: string) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.endsWith("/auth/me")) {
      return jsonResponse({
        user: {
          id: "user-a",
          platform_role: role === "PLATFORM_ADMIN" ? role : null,
          status: "active",
        },
        memberships: [
          {
            id: "membership-a",
            organization_id: "org-a",
            role,
            status: "active",
          },
        ],
      });
    }
    if (path.endsWith("/organizations")) {
      return jsonResponse({ items: [organization] });
    }
    if (path.endsWith("/memberships")) {
      return jsonResponse({
        items: [
          {
            id: "membership-a",
            organization_id: "org-a",
            user_id: "user-a-id",
            username: "local-staff-a",
            display_name: "本機工作人員 A",
            role: "STAFF",
            status: "active",
            medical_care_access: false,
          },
        ],
      });
    }
    if (path.endsWith("/areas")) {
      return jsonResponse({ items: [] });
    }
    return jsonResponse({});
  });
}

let root: Root | undefined;
let container: HTMLDivElement | undefined;

async function renderPage(role: string) {
  vi.stubGlobal("fetch", mockFetch(role));
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(<SheltersManagementPage />);
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

describe("shelter management page authorization", () => {
  it("only shows organization creation to PLATFORM_ADMIN", async () => {
    await renderPage("PLATFORM_ADMIN");
    expect(container?.textContent).toContain("建立收容所");
  });

  it("shows current shelter settings but not organization creation to SHELTER_ADMIN", async () => {
    await renderPage("SHELTER_ADMIN");
    expect(container?.textContent).toContain(
      "台灣各地收容所統一使用 Asia/Taipei",
    );
    expect(container?.textContent).toContain("帳號與權限");
    expect(container?.textContent).not.toContain("建立收容所");
    expect(container?.textContent).toContain("本機工作人員 A");
    expect(container?.textContent).toContain("帳號：local-staff-a");
    expect(container?.textContent).toContain("管理人員");
    expect(container?.textContent).toContain("志工");
    expect(container?.textContent).toContain("查看已封存成員");
    expect(container?.textContent).toContain("建立帳號");
    expect(container?.textContent).not.toContain("照護日期與時區");
    expect(container?.textContent).not.toContain("儲存時區");
  });

  it("does not expose shelter settings to STAFF", async () => {
    await renderPage("STAFF");
    expect(container?.textContent).not.toContain("照護日期與時區");
    expect(container?.textContent).not.toContain("帳號與權限");
    expect(container?.textContent).not.toContain("建立收容所");
  });

  it("opens and closes the account creation modal from the page header", async () => {
    await renderPage("SHELTER_ADMIN");
    const createButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "建立帳號");
    expect(createButton).toBeDefined();
    await act(async () => createButton?.click());
    expect(container?.textContent).toContain("建立機構帳號");
    expect(container?.querySelector('[role="dialog"]')).not.toBeNull();
    const cancelButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "取消");
    await act(async () => cancelButton?.click());
    expect(
      container?.querySelector<HTMLDialogElement>('[role="dialog"]')?.open,
    ).toBe(false);
  });
});
