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

function mockFetch(
  role: string,
  delayMs = 0,
  mutationDelayMs = 0,
  areas: Array<{
    id: string;
    name: string;
    area_type: "area" | "cage";
    status: "active" | "inactive";
  }> = [],
  detailsDelayMs = 0,
) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (delayMs) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
    if (
      detailsDelayMs &&
      (path.endsWith("/memberships") || path.endsWith("/areas"))
    ) {
      await new Promise((resolve) => setTimeout(resolve, detailsDelayMs));
    }
    if (mutationDelayMs && init?.method && init.method !== "GET") {
      await new Promise((resolve) => setTimeout(resolve, mutationDelayMs));
    }
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
            id: "membership-admin",
            organization_id: "org-a",
            user_id: "user-admin-id",
            username: "local-admin-a",
            display_name: "本機管理員 A",
            role: "SHELTER_ADMIN",
            status: "active",
            access_version: 1,
            medical_care_access: false,
          },
          {
            id: "membership-staff",
            organization_id: "org-a",
            user_id: "user-staff-id",
            username: "local-staff-a",
            display_name: "本機工作人員 A",
            role: "STAFF",
            status: "disabled",
            access_version: 1,
            medical_care_access: false,
          },
          {
            id: "membership-volunteer",
            organization_id: "org-a",
            user_id: "user-volunteer-id",
            username: "local-volunteer-a",
            display_name: "本機志工 A",
            role: "VOLUNTEER",
            status: "active",
            access_version: 1,
            medical_care_access: false,
            volunteer_authorization_status: "active",
          },
          {
            id: "membership-revoked",
            organization_id: "org-a",
            user_id: "user-revoked-id",
            username: "local-volunteer-revoked",
            display_name: "本機撤銷志工",
            role: "VOLUNTEER",
            status: "disabled",
            access_version: 1,
            medical_care_access: false,
            volunteer_authorization_status: "revoked",
          },
        ],
      });
    }
    if (path.endsWith("/areas")) {
      return jsonResponse({ items: areas });
    }
    return jsonResponse({});
  });
}

let root: Root | undefined;
let container: HTMLDivElement | undefined;

async function renderPage(
  role: string,
  delayMs = 0,
  mutationDelayMs = 0,
  areas: Array<{
    id: string;
    name: string;
    area_type: "area" | "cage";
    status: "active" | "inactive";
  }> = [],
  detailsDelayMs = 0,
) {
  const fetchMock = mockFetch(
    role,
    delayMs,
    mutationDelayMs,
    areas,
    detailsDelayMs,
  );
  vi.stubGlobal("fetch", fetchMock);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(<SheltersManagementPage />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  return fetchMock;
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

  it("shows current shelter permissions but not organization creation to SHELTER_ADMIN", async () => {
    await renderPage("SHELTER_ADMIN");
    expect(container?.textContent).toContain("帳號與權限");
    expect(container?.textContent).not.toContain("建立收容所");
    expect(container?.textContent).toContain("本機工作人員 A");
    expect(container?.textContent).toContain("帳號：local-staff-a");
    expect(container?.textContent).toContain("工作人員");
    expect(container?.textContent).toContain("志工");
    expect(container?.textContent).toContain("授權已撤銷");
    expect(container?.textContent).not.toContain("時區");
    expect(container?.textContent).toContain("查看已封存成員");
    expect(container?.textContent).toContain("建立帳號");
    expect(container?.textContent).not.toContain("照護日期與時區");
    expect(container?.textContent).not.toContain("儲存時區");
    expect(container?.textContent).toContain("目前沒有籠舍或區域");
    const sectionTitles = Array.from(
      container?.querySelectorAll(".membership-section h3") ?? [],
    ).map((heading) => heading.textContent?.trim());
    expect(sectionTitles).toEqual(["志工", "工作人員"]);
    expect(container?.querySelectorAll(".membership-item-muted").length).toBe(
      2,
    );
    expect(
      Array.from(container?.querySelectorAll("button") ?? []).filter(
        (button) => button.textContent?.trim() === "重新啟用",
      ),
    ).toHaveLength(1);
  });

  it("renders shelter areas as localized standard list rows", async () => {
    await renderPage("SHELTER_ADMIN", 0, 0, [
      {
        id: "area-a",
        name: "隔離區",
        area_type: "area",
        status: "active",
      },
      {
        id: "cage-a",
        name: "A-01",
        area_type: "cage",
        status: "inactive",
      },
    ]);

    expect(container?.querySelector("#area-list-title")?.textContent).toBe(
      "籠舍／區域",
    );
    const list = container?.querySelector('[aria-label="籠舍與區域清單"]');
    const rows = list?.querySelectorAll(".list-card.area-item");
    expect(rows).toHaveLength(2);
    expect(rows?.[0]?.textContent).toContain("隔離區");
    expect(rows?.[0]?.textContent).toContain("區域");
    expect(rows?.[0]?.textContent).toContain("啟用中");
    expect(rows?.[1]?.textContent).toContain("A-01");
    expect(rows?.[1]?.textContent).toContain("籠舍");
    expect(rows?.[1]?.textContent).toContain("已停用");
    expect(list?.querySelectorAll(".ui-badge")).toHaveLength(4);
  });

  it("shows loading before shelter and membership responses resolve", async () => {
    await renderPage(
      "SHELTER_ADMIN",
      0,
      0,
      [
        {
          id: "pending-area",
          name: "尚未完成載入的區域",
          area_type: "area",
          status: "active",
        },
      ],
      40,
    );
    expect(container?.textContent).toContain("正在載入籠舍與區域");
    expect(container?.textContent).not.toContain("目前沒有志工");
    expect(container?.textContent).not.toContain("目前沒有籠舍或區域");
    expect(container?.textContent).not.toContain("尚未完成載入的區域");
  });

  it("prevents duplicate shelter mutation form submissions", async () => {
    const fetchMock = await renderPage("SHELTER_ADMIN", 0, 80);
    const areaInput = container?.querySelector<HTMLInputElement>("#area-name");
    await act(async () => {
      if (!areaInput) return;
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )?.set;
      setter?.call(areaInput, "隔離區");
      areaInput.dispatchEvent(new Event("input", { bubbles: true }));
      areaInput.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const form = areaInput?.closest("form");

    await act(async () => {
      form?.dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
      form?.dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    const mutationCalls = fetchMock.mock.calls.filter(
      ([input, init]) =>
        String(input).endsWith("/areas") && init?.method === "POST",
    );
    expect(mutationCalls).toHaveLength(1);
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

  it("opens a confirmation dialog before a membership role mutation", async () => {
    await renderPage("SHELTER_ADMIN");
    const roleSelect = container?.querySelector<HTMLSelectElement>(
      '[aria-label="本機工作人員 A 角色"]',
    );
    expect(roleSelect).not.toBeNull();
    await act(async () => {
      if (!roleSelect) return;
      roleSelect.value = "SHELTER_ADMIN";
      roleSelect.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(container?.querySelector('[role="alertdialog"]')).not.toBeNull();
    expect(container?.textContent).toContain("調整角色");
    const cancelButton = Array.from(
      container?.querySelectorAll('[role="alertdialog"] button') ?? [],
    ).find((button) => button.textContent?.trim() === "取消") as
      HTMLButtonElement | undefined;
    await act(async () => cancelButton?.click());
    expect(
      container?.querySelector<HTMLDialogElement>('[role="alertdialog"]')?.open,
    ).toBe(false);
  });

  it("switches from account form to admin confirmation without stacking dialogs", async () => {
    await renderPage("SHELTER_ADMIN");
    const createButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "建立帳號");
    await act(async () => createButton?.click());

    const roleSelect =
      container?.querySelector<HTMLSelectElement>("#account-role");
    await act(async () => {
      if (!roleSelect) return;
      roleSelect.value = "SHELTER_ADMIN";
      roleSelect.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const accountForm = container?.querySelector<HTMLFormElement>(
      '[role="dialog"] form',
    );
    await act(async () =>
      accountForm?.dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      ),
    );

    expect(container?.querySelector('[role="alertdialog"]')).not.toBeNull();
    expect(
      container?.querySelector<HTMLDialogElement>('[role="dialog"]')?.open,
    ).toBe(false);

    const openAlertDialog = Array.from(
      container?.querySelectorAll<HTMLDialogElement>('[role="alertdialog"]') ??
        [],
    ).find((dialog) => dialog.open);
    const cancelButton = Array.from(
      openAlertDialog?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "取消") as
      HTMLButtonElement | undefined;
    await act(async () => cancelButton?.click());
    expect(
      container?.querySelector<HTMLDialogElement>('[role="alertdialog"]')?.open,
    ).toBe(false);
    expect(
      container?.querySelector<HTMLDialogElement>('[role="dialog"]')?.open,
    ).toBe(true);
  });
});
