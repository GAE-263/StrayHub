// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ManagementQrCodeListItem } from "../../../../lib/qr-management";
import QrCodesPage from "./page";

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

const activeQr: ManagementQrCodeListItem = {
  id: "11111111-1111-4111-8111-111111111111",
  organization_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  animal_id: "22222222-2222-4222-8222-222222222222",
  animal_name: "阿福",
  shelter_number: "DOG-001",
  animal_status: "active",
  area_name: "犬舍 A 區",
  status: "active",
  revoked: false,
  created_at: "2026-08-20T06:30:00Z",
  deep_link: "https://example.test/qr/qr-1",
  token: null,
};

const legacyActiveQr: ManagementQrCodeListItem = {
  ...activeQr,
  id: "33333333-3333-4333-8333-333333333333",
  animal_id: "44444444-4444-4444-8444-444444444444",
  animal_name: "小黑",
  shelter_number: null,
  area_name: null,
  deep_link: null,
};

const inactiveAnimalQr: ManagementQrCodeListItem = {
  ...activeQr,
  id: "55555555-5555-4555-8555-555555555555",
  animal_id: "66666666-6666-4666-8666-666666666666",
  animal_name: "豆豆",
  animal_status: "inactive",
};

const unknownStatusAnimalQr: ManagementQrCodeListItem = {
  ...activeQr,
  id: "99999999-9999-4999-8999-999999999999",
  animal_id: "10101010-1010-4010-8010-101010101010",
  animal_name: "未來狀態動物",
  animal_status: "future-status",
};

const revokedQr: ManagementQrCodeListItem = {
  ...activeQr,
  id: "77777777-7777-4777-8777-777777777777",
  animal_id: "88888888-8888-4888-8888-888888888888",
  animal_name: "花花",
  status: "revoked",
  revoked: true,
  deep_link: null,
};

const adminProfile = {
  user: { id: "user-a", platform_role: null, status: "active" },
  memberships: [
    {
      id: "membership-a",
      organization_id: "org-a",
      user_id: "user-a",
      role: "SHELTER_ADMIN",
      status: "active",
    },
  ],
};

const staffProfile = {
  ...adminProfile,
  memberships: [{ ...adminProfile.memberships[0], role: "STAFF" }],
};

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

type RenderOptions = {
  items?: ManagementQrCodeListItem[];
  total?: number;
  profile?: typeof adminProfile;
  qrStatus?: number;
  revokeStatus?: number;
};

let root: Root | undefined;
let container: HTMLDivElement | undefined;

function mountPage() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  root.render(<QrCodesPage />);
}

async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

async function renderPage({
  items = [activeQr, legacyActiveQr, inactiveAnimalQr, revokedQr],
  total = items.length,
  profile = adminProfile,
  qrStatus = 200,
  revokeStatus = 200,
}: RenderOptions = {}) {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith("/auth/active-shelter-context"))
        return response({ organization_id: "org-a" });
      if (path.endsWith("/auth/me")) return response(profile);
      if (path.endsWith("/revoke")) return response(revokedQr, revokeStatus);
      if (path.endsWith("/regenerate")) return response(activeQr);
      if (path.includes("/qr-codes?") && !init?.method)
        return response({ items, page: 1, page_size: 20, total }, qrStatus);
      return response({}, 404);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  await act(async () => {
    mountPage();
    await settle();
  });
  return fetchMock;
}

function recordNamed(name: string) {
  return Array.from(container?.querySelectorAll("li") ?? []).find((record) =>
    record.querySelector("h3")?.textContent?.includes(name),
  );
}

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  container?.remove();
  container = undefined;
  vi.unstubAllGlobals();
});

describe("animal-aware care QR management list", () => {
  it("requests the fixed QR-2B list and presents animal identity without UUIDs", async () => {
    const fetchMock = await renderPage();

    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/management/qr-codes?status=all&page=1&page_size=20",
      expect.anything(),
    );
    expect(container?.textContent).toContain(
      "僅顯示目前操作收容所的 QR 紀錄。",
    );
    expect(container?.textContent).toContain("阿福");
    expect(container?.textContent).toContain("收容編號：DOG-001");
    expect(container?.textContent).toContain("區域：犬舍 A 區");
    expect(container?.textContent).not.toContain(activeQr.animal_id);
    expect(container?.querySelector("input")).toBeNull();
    expect(
      recordNamed("阿福")?.querySelector("h3 a")?.getAttribute("href"),
    ).toBe(`/animals/${activeQr.animal_id}`);
  });

  it("renders null fallbacks, localized statuses, and a readable created time", async () => {
    await renderPage();
    const legacyRecord = recordNamed("小黑");
    const inactiveRecord = recordNamed("豆豆");

    expect(legacyRecord?.textContent).toContain("收容編號：未提供");
    expect(legacyRecord?.textContent).toContain("區域：未分配");
    expect(legacyRecord?.textContent).toContain("QR 使用中");
    expect(legacyRecord?.textContent).toContain("啟用中");
    expect(legacyRecord?.textContent).toContain("2026/08/20 14:30");
    expect(inactiveRecord?.textContent).toContain("已停用");
    expect(recordNamed("花花")?.textContent).toContain("QR 已撤銷");
  });

  it("applies the admin action matrix to active, legacy, non-active, and revoked records", async () => {
    await renderPage();
    const active = recordNamed("阿福");
    const legacy = recordNamed("小黑");
    const inactive = recordNamed("豆豆");
    const revoked = recordNamed("花花");

    expect(active?.textContent).toContain("前往重新列印");
    expect(active?.textContent).toContain("重新產生新 QR");
    expect(active?.textContent).toContain("撤銷 QR");
    expect(legacy?.textContent).toContain("舊版 QR 無法重新列印");
    expect(legacy?.textContent).toContain("重新產生新 QR");
    expect(legacy?.textContent).toContain("撤銷 QR");
    expect(inactive?.textContent).toContain("前往動物檔案");
    expect(inactive?.textContent).toContain("撤銷 QR");
    expect(inactive?.textContent).not.toContain("重新產生");
    expect(inactive?.textContent).not.toContain("重新列印");
    expect(revoked?.textContent).toContain("前往動物檔案");
    expect(revoked?.textContent).not.toContain("撤銷 QR");
    expect(revoked?.textContent).not.toContain("重新產生");
  });

  it("keeps staff records read-only except for safe profile and reprint navigation", async () => {
    await renderPage({ profile: staffProfile });

    expect(recordNamed("阿福")?.textContent).toContain("前往重新列印");
    expect(recordNamed("小黑")?.textContent).toContain("舊版 QR 無法重新列印");
    expect(recordNamed("豆豆")?.textContent).toContain("前往動物檔案");
    expect(recordNamed("花花")?.textContent).toContain("前往動物檔案");
    expect(container?.textContent).not.toContain("重新產生新 QR");
    expect(container?.textContent).not.toContain("撤銷 QR");
  });

  it("fails an unknown animal status closed while preserving admin revoke", async () => {
    await renderPage({ items: [unknownStatusAnimalQr] });
    const record = recordNamed("未來狀態動物");

    expect(record?.textContent).toContain("future-status");
    expect(record?.textContent).toContain("前往動物檔案");
    expect(record?.textContent).toContain("撤銷 QR");
    expect(record?.textContent).not.toContain("重新列印");
    expect(record?.textContent).not.toContain("重新產生");
  });

  it("implements reprint as profile navigation without a mutation action", async () => {
    const fetchMock = await renderPage({ items: [activeQr] });
    const reprintLink = Array.from(
      recordNamed("阿福")?.querySelectorAll("a") ?? [],
    ).find((link) => link.textContent?.includes("前往重新列印"));

    expect(reprintLink?.getAttribute("href")).toBe(
      `/animals/${activeQr.animal_id}`,
    );
    expect(reprintLink?.tagName).toBe("A");
    expect(
      fetchMock.mock.calls.some(
        ([path, init]) =>
          init?.method === "POST" && String(path).includes("/qr-codes"),
      ),
    ).toBe(false);
  });

  it("uses the animal name in the existing destructive confirmation guidance", async () => {
    await renderPage({ items: [activeQr] });
    const revokeButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "撤銷 QR");

    await act(async () => revokeButton?.click());

    expect(container?.textContent).toContain("確認撤銷 QR");
    expect(container?.textContent).toContain("動物：阿福");
    expect(container?.textContent).toContain("不會建立新的 QR");
    expect(container?.textContent).not.toContain(activeQr.animal_id);
  });

  it("preserves regenerate invalidation warning and replacement guidance", async () => {
    const fetchMock = await renderPage({ items: [activeQr] });
    const regenerateButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "重新產生新 QR");

    await act(async () => regenerateButton?.click());
    expect(container?.textContent).toContain("目前的 QR 會立即失效");
    const confirmButton = Array.from(
      container?.querySelectorAll<HTMLButtonElement>("dialog button") ?? [],
    ).find((button) => button.textContent?.trim() === "重新產生新 QR");
    await act(async () => {
      confirmButton?.click();
      await settle();
    });

    expect(
      fetchMock.mock.calls.some(
        ([path, init]) =>
          String(path).endsWith(`/${activeQr.id}/regenerate`) &&
          init?.method === "POST",
      ),
    ).toBe(true);
    expect(container?.textContent).toContain(
      "QR 已重新產生，請至動物檔案列印並更換舊標籤。",
    );
  });

  it("keeps the list visible when a confirmed mutation fails", async () => {
    await renderPage({ items: [activeQr], revokeStatus: 500 });
    const revokeButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "撤銷 QR");
    await act(async () => revokeButton?.click());
    const confirmButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "確認撤銷");

    await act(async () => {
      confirmButton?.click();
      await settle();
    });

    expect(container?.textContent).toContain("QR 撤銷失敗（HTTP 500）");
    expect(recordNamed("阿福")?.textContent).toContain("前往重新列印");
  });

  it("shows an explicit interim notice when more records exist than are rendered", async () => {
    await renderPage({ items: [activeQr], total: 43 });

    expect(container?.textContent).toContain(
      "目前顯示前 1 筆 QR 紀錄；完整分頁將於後續管理功能提供。",
    );
  });

  it("does not show the interim notice when total equals rendered records", async () => {
    await renderPage({ items: [activeQr], total: 1 });

    expect(container?.textContent).not.toContain(
      "完整分頁將於後續管理功能提供",
    );
  });

  it("renders the empty state without filter-oriented copy", async () => {
    await renderPage({ items: [] });

    expect(container?.textContent).toContain("目前收容所尚無照護 QR 紀錄。");
    expect(container?.textContent).toContain("請前往動物檔案建立照護 QR。");
  });

  it("renders permission denial as a distinct state", async () => {
    await renderPage({ qrStatus: 403 });
    expect(container?.textContent).toContain("沒有查看權限");
    expect(container?.textContent).toContain("目前收容所 QR 紀錄的權限");
  });

  it("renders a retryable general load error", async () => {
    await renderPage({ qrStatus: 500 });
    expect(container?.textContent).toContain("QR 清單載入失敗");
    expect(container?.textContent).toContain("HTTP 500");
    expect(container?.textContent).toContain("重新載入");
  });

  it("keeps loading visible until the list request resolves", async () => {
    let resolveQr!: (value: Response) => void;
    const qrPromise = new Promise<Response>((resolve) => {
      resolveQr = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path.includes("/qr-codes?")) return qrPromise;
        if (path.endsWith("/auth/active-shelter-context"))
          return Promise.resolve(response({ organization_id: "org-a" }));
        return Promise.resolve(response(adminProfile));
      }),
    );

    await act(async () => {
      mountPage();
      await settle();
    });
    expect(container?.textContent).toContain("正在載入 QR…");

    await act(async () => {
      resolveQr(response({ items: [], page: 1, page_size: 20, total: 0 }));
      await settle();
    });
    expect(container?.textContent).toContain("目前收容所尚無照護 QR 紀錄。");
  });
});
