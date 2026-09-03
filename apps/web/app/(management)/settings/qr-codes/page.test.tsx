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
  listHandler?: (url: URL, init?: RequestInit) => Response | Promise<Response>;
  revokeHandler?: () => Response | Promise<Response>;
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
  for (let index = 0; index < 8; index += 1) await Promise.resolve();
}

async function renderPage({
  items = [activeQr, legacyActiveQr, inactiveAnimalQr, revokedQr],
  total = items.length,
  profile = adminProfile,
  qrStatus = 200,
  revokeStatus = 200,
  listHandler,
  revokeHandler,
}: RenderOptions = {}) {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith("/auth/active-shelter-context"))
        return response({ organization_id: "org-a" });
      if (path.endsWith("/auth/me")) return response(profile);
      if (path.endsWith("/revoke"))
        return revokeHandler?.() ?? response(revokedQr, revokeStatus);
      if (path.endsWith("/regenerate")) return response(activeQr);
      if (path.includes("/qr-codes?") && !init?.method) {
        const url = new URL(path, "http://localhost");
        if (listHandler) return listHandler(url, init);
        return response(
          {
            items,
            page: Number(url.searchParams.get("page")),
            page_size: 20,
            total,
          },
          qrStatus,
        );
      }
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

function setControlValue(
  control: HTMLInputElement | HTMLSelectElement,
  value: string,
) {
  const prototype =
    control instanceof HTMLInputElement
      ? HTMLInputElement.prototype
      : HTMLSelectElement.prototype;
  Object.getOwnPropertyDescriptor(prototype, "value")?.set?.call(
    control,
    value,
  );
  control.dispatchEvent(
    new Event(control instanceof HTMLSelectElement ? "change" : "input", {
      bubbles: true,
    }),
  );
}

async function changeControl(id: string, value: string) {
  const control = container?.querySelector<
    HTMLInputElement | HTMLSelectElement
  >(`#${id}`);
  await act(async () => {
    if (control) setControlValue(control, value);
    await settle();
  });
}

async function clickButton(name: string) {
  const button = Array.from(
    container?.querySelectorAll<HTMLButtonElement>("button") ?? [],
  ).find((candidate) => candidate.textContent?.trim() === name);
  await act(async () => {
    button?.click();
    await settle();
  });
}

async function advance(milliseconds: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(milliseconds);
    await settle();
  });
}

function qrListUrls(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls
    .map(([input]) => String(input))
    .filter((path) => path.includes("/management/qr-codes?"))
    .map((path) => new URL(path, "http://localhost"));
}

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  container?.remove();
  container = undefined;
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("animal-aware care QR management list", () => {
  it("requests the default QR-2C list and presents animal identity without UUIDs", async () => {
    const fetchMock = await renderPage();

    expect(qrListUrls(fetchMock).at(0)?.search).toBe(
      "?page=1&page_size=20&status=all",
    );
    expect(container?.textContent).toContain(
      "僅顯示目前操作收容所的 QR 紀錄。",
    );
    expect(container?.textContent).toContain("阿福");
    expect(container?.textContent).toContain("收容編號：DOG-001");
    expect(container?.textContent).toContain("區域：犬舍 A 區");
    expect(container?.textContent).not.toContain(activeQr.animal_id);
    expect(container?.querySelector("input")?.getAttribute("type")).toBe(
      "search",
    );
    expect(
      recordNamed("阿福")?.querySelector("h3 a")?.getAttribute("href"),
    ).toBe(`/animals/${activeQr.animal_id}`);
  });

  it("debounces search for 300ms, cancels the prior value, and trims the request", async () => {
    vi.useFakeTimers();
    const fetchMock = await renderPage();
    expect(qrListUrls(fetchMock)).toHaveLength(1);

    await changeControl("qr-query", "小");
    await advance(299);
    expect(qrListUrls(fetchMock)).toHaveLength(1);

    await changeControl("qr-query", "  小黑  ");
    await advance(299);
    expect(qrListUrls(fetchMock)).toHaveLength(1);
    await advance(1);

    const urls = qrListUrls(fetchMock);
    expect(urls).toHaveLength(2);
    expect(urls.at(-1)?.searchParams.get("query")).toBe("小黑");
    expect(urls.some((url) => url.searchParams.get("query") === "小")).toBe(
      false,
    );
  });

  it("clears a pending debounce timer when the page unmounts", async () => {
    vi.useFakeTimers();
    const fetchMock = await renderPage();

    await changeControl("qr-query", "不應送出");
    await act(async () => root?.unmount());
    root = undefined;
    await advance(300);

    expect(qrListUrls(fetchMock)).toHaveLength(1);
  });

  it("supports previous and next pagination with correct disabled states", async () => {
    const fetchMock = await renderPage({
      listHandler: (url) => {
        const requestedPage = Number(url.searchParams.get("page"));
        return response({
          items: [
            requestedPage === 1
              ? activeQr
              : { ...legacyActiveQr, animal_name: "第二頁動物" },
          ],
          page: requestedPage,
          page_size: 20,
          total: 21,
        });
      },
    });

    const previous = Array.from(
      container?.querySelectorAll<HTMLButtonElement>("button") ?? [],
    ).find((button) => button.textContent?.trim() === "上一頁");
    const next = Array.from(
      container?.querySelectorAll<HTMLButtonElement>("button") ?? [],
    ).find((button) => button.textContent?.trim() === "下一頁");
    expect(previous?.disabled).toBe(true);
    expect(next?.disabled).toBe(false);

    await clickButton("下一頁");
    expect(recordNamed("第二頁動物")).toBeDefined();
    expect(container?.textContent).toContain("第 2 頁，共 21 筆");
    expect(
      Array.from(
        container?.querySelectorAll<HTMLButtonElement>("button") ?? [],
      ).find((button) => button.textContent?.trim() === "下一頁")?.disabled,
    ).toBe(true);
    expect(qrListUrls(fetchMock).at(-1)?.searchParams.get("page")).toBe("2");

    await clickButton("上一頁");
    expect(recordNamed("阿福")).toBeDefined();
    expect(qrListUrls(fetchMock).at(-1)?.searchParams.get("page")).toBe("1");
  });

  it("reconciles an overlarge page to the last page when total remains positive", async () => {
    let pageTwoRequests = 0;
    const fetchMock = await renderPage({
      listHandler: (url) => {
        const requestedPage = Number(url.searchParams.get("page"));
        if (requestedPage === 3)
          return response({ items: [], page: 3, page_size: 20, total: 21 });
        if (requestedPage === 2) pageTwoRequests += 1;
        return response({
          items: [
            {
              ...activeQr,
              animal_name:
                pageTwoRequests > 1 ? "校正後最後一頁" : "第二頁舊結果",
            },
          ],
          page: requestedPage,
          page_size: 20,
          total: pageTwoRequests > 1 ? 21 : 81,
        });
      },
    });

    await clickButton("下一頁");
    await clickButton("下一頁");

    expect(recordNamed("校正後最後一頁")).toBeDefined();
    expect(container?.textContent).toContain("第 2 頁，共 21 筆");
    const pages = qrListUrls(fetchMock).map((url) =>
      url.searchParams.get("page"),
    );
    expect(pages.slice(-2)).toEqual(["3", "2"]);
  });

  it("reconciles an overlarge page to page one when the result total is zero", async () => {
    let initialRequest = true;
    const fetchMock = await renderPage({
      listHandler: (url) => {
        const requestedPage = Number(url.searchParams.get("page"));
        if (initialRequest) {
          initialRequest = false;
          return response({
            items: [activeQr],
            page: 1,
            page_size: 20,
            total: 21,
          });
        }
        return response({
          items: [],
          page: requestedPage,
          page_size: 20,
          total: 0,
        });
      },
    });

    await clickButton("下一頁");

    expect(container?.textContent).toContain("目前收容所尚無照護 QR 紀錄。");
    const pages = qrListUrls(fetchMock).map((url) =>
      url.searchParams.get("page"),
    );
    expect(pages.slice(-2)).toEqual(["2", "1"]);
  });

  it("resets page to one when the debounced search changes", async () => {
    vi.useFakeTimers();
    const fetchMock = await renderPage({ items: [activeQr], total: 41 });
    await clickButton("下一頁");
    await clickButton("下一頁");
    expect(qrListUrls(fetchMock).at(-1)?.searchParams.get("page")).toBe("3");

    await changeControl("qr-query", "小黑");
    await advance(300);

    const latest = qrListUrls(fetchMock).at(-1);
    expect(latest?.searchParams.get("query")).toBe("小黑");
    expect(latest?.searchParams.get("page")).toBe("1");
    expect(
      qrListUrls(fetchMock).some(
        (url) =>
          url.searchParams.get("query") === "小黑" &&
          url.searchParams.get("page") === "3",
      ),
    ).toBe(false);
  });

  it("resets page to one when status changes", async () => {
    const fetchMock = await renderPage({ items: [activeQr], total: 41 });
    await clickButton("下一頁");
    await clickButton("下一頁");

    await changeControl("qr-status", "revoked");

    const latest = qrListUrls(fetchMock).at(-1);
    expect(latest?.searchParams.get("status")).toBe("revoked");
    expect(latest?.searchParams.get("page")).toBe("1");
    expect(
      qrListUrls(fetchMock).some(
        (url) =>
          url.searchParams.get("status") === "revoked" &&
          url.searchParams.get("page") === "3",
      ),
    ).toBe(false);
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

  it("reconciles an emptied active-filter page after revoke", async () => {
    let revoked = false;
    const fetchMock = await renderPage({
      revokeHandler: () => {
        revoked = true;
        return response(revokedQr);
      },
      listHandler: (url) => {
        const requestedPage = Number(url.searchParams.get("page"));
        const activeFilter = url.searchParams.get("status") === "active";
        if (activeFilter && requestedPage === 2 && revoked)
          return response({ items: [], page: 2, page_size: 20, total: 20 });
        return response({
          items: [activeQr],
          page: requestedPage,
          page_size: 20,
          total: activeFilter ? (revoked ? 20 : 21) : 1,
        });
      },
    });

    await changeControl("qr-status", "active");
    await clickButton("下一頁");
    await clickButton("撤銷 QR");
    await clickButton("確認撤銷");

    expect(container?.textContent).toContain("共 20 筆");
    expect(container?.textContent).not.toContain("上一頁");
    const activeUrls = qrListUrls(fetchMock).filter(
      (url) => url.searchParams.get("status") === "active",
    );
    expect(activeUrls.at(-2)?.searchParams.get("page")).toBe("2");
    expect(activeUrls.at(-1)?.searchParams.get("page")).toBe("1");
  });

  it("keeps a valid all-status page after revoke and trusts the refreshed row", async () => {
    let revoked = false;
    const fetchMock = await renderPage({
      revokeHandler: () => {
        revoked = true;
        return response(revokedQr);
      },
      listHandler: (url) => {
        const requestedPage = Number(url.searchParams.get("page"));
        return response({
          items: [
            requestedPage === 2 && revoked
              ? { ...revokedQr, animal_name: "第二頁已撤銷結果" }
              : activeQr,
          ],
          page: requestedPage,
          page_size: 20,
          total: 21,
        });
      },
    });

    await clickButton("下一頁");
    await clickButton("撤銷 QR");
    await clickButton("確認撤銷");

    expect(recordNamed("第二頁已撤銷結果")).toBeDefined();
    expect(container?.textContent).toContain("第 2 頁，共 21 筆");
    expect(qrListUrls(fetchMock).at(-1)?.searchParams.get("page")).toBe("2");
  });

  it("shows filtered empty on page one when revoke removes the final active QR", async () => {
    let revoked = false;
    await renderPage({
      revokeHandler: () => {
        revoked = true;
        return response(revokedQr);
      },
      listHandler: (url) => {
        const activeFilter = url.searchParams.get("status") === "active";
        return response({
          items: activeFilter && revoked ? [] : [activeQr],
          page: 1,
          page_size: 20,
          total: activeFilter && revoked ? 0 : 1,
        });
      },
    });

    await changeControl("qr-status", "active");
    await clickButton("撤銷 QR");
    await clickButton("確認撤銷");

    expect(container?.textContent).toContain("找不到符合條件的 QR 紀錄。");
    expect(container?.textContent).not.toContain(
      "目前收容所尚無照護 QR 紀錄。",
    );
  });

  it("does not let a pre-mutation list response overwrite refreshed truth", async () => {
    let resolveMutation!: (value: Response) => void;
    let resolveOldList!: (value: Response) => void;
    let activeRequests = 0;
    await renderPage({
      revokeHandler: () =>
        new Promise<Response>((resolve) => {
          resolveMutation = resolve;
        }),
      listHandler: (url) => {
        if (url.searchParams.get("status") === "active") {
          activeRequests += 1;
          if (activeRequests === 1)
            return new Promise<Response>((resolve) => {
              resolveOldList = resolve;
            });
          return response({
            items: [{ ...activeQr, animal_name: "撤銷後伺服器結果" }],
            page: 1,
            page_size: 20,
            total: 1,
          });
        }
        return response({
          items: [activeQr],
          page: 1,
          page_size: 20,
          total: 1,
        });
      },
    });

    await clickButton("撤銷 QR");
    await clickButton("確認撤銷");
    await changeControl("qr-status", "active");
    await act(async () => {
      resolveMutation(response(revokedQr));
      await settle();
    });
    expect(recordNamed("撤銷後伺服器結果")).toBeDefined();

    await act(async () => {
      resolveOldList(
        response({
          items: [{ ...activeQr, animal_name: "撤銷前過期結果" }],
          page: 1,
          page_size: 20,
          total: 1,
        }),
      );
      await settle();
    });
    expect(recordNamed("撤銷後伺服器結果")).toBeDefined();
    expect(recordNamed("撤銷前過期結果")).toBeUndefined();
  });

  it("removes the interim first-N notice when pagination is unnecessary", async () => {
    await renderPage({ items: [activeQr], total: 20 });

    expect(container?.textContent).not.toContain(
      "完整分頁將於後續管理功能提供",
    );
    expect(container?.textContent).not.toContain("上一頁");
  });

  it("shows a search-specific empty state and resets filters", async () => {
    vi.useFakeTimers();
    const fetchMock = await renderPage({
      listHandler: (url) =>
        response({
          items: url.searchParams.has("query") ? [] : [activeQr],
          page: 1,
          page_size: 20,
          total: url.searchParams.has("query") ? 0 : 1,
        }),
    });

    await changeControl("qr-query", "不存在");
    await advance(300);
    expect(container?.textContent).toContain("找不到符合條件的 QR 紀錄。");
    expect(container?.textContent).not.toContain(
      "目前收容所尚無照護 QR 紀錄。",
    );

    await clickButton("重設篩選");
    expect(recordNamed("阿福")).toBeDefined();
    expect(qrListUrls(fetchMock).at(-1)?.searchParams.has("query")).toBe(false);
  });

  it("shows a filtered empty state for a status with no records", async () => {
    await renderPage({
      listHandler: (url) => {
        const filteredStatus = url.searchParams.get("status") !== "all";
        return response({
          items: filteredStatus ? [] : [activeQr],
          page: 1,
          page_size: 20,
          total: filteredStatus ? 0 : 1,
        });
      },
    });

    await changeControl("qr-status", "revoked");
    expect(container?.textContent).toContain("找不到符合條件的 QR 紀錄。");
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

  it("keeps the newest search response when an older request returns late", async () => {
    vi.useFakeTimers();
    let resolveOld!: (value: Response) => void;
    const oldRequest: { signal: AbortSignal | null } = { signal: null };
    const fetchMock = await renderPage({
      listHandler: (url, init) => {
        const query = url.searchParams.get("query");
        if (query === "小") {
          oldRequest.signal = init?.signal ?? null;
          return new Promise<Response>((resolve) => {
            resolveOld = resolve;
          });
        }
        if (query === "小黑")
          return response({
            items: [{ ...legacyActiveQr, animal_name: "小黑新結果" }],
            page: 1,
            page_size: 20,
            total: 1,
          });
        return response({
          items: [activeQr],
          page: 1,
          page_size: 20,
          total: 1,
        });
      },
    });

    await changeControl("qr-query", "小");
    await advance(300);
    await changeControl("qr-query", "小黑");
    await advance(300);
    expect(recordNamed("小黑新結果")).toBeDefined();
    expect(oldRequest.signal?.aborted).toBe(true);

    await act(async () => {
      resolveOld(
        response({
          items: [{ ...activeQr, animal_name: "過期搜尋結果" }],
          page: 1,
          page_size: 20,
          total: 1,
        }),
      );
      await settle();
    });
    expect(recordNamed("小黑新結果")).toBeDefined();
    expect(recordNamed("過期搜尋結果")).toBeUndefined();
    expect(qrListUrls(fetchMock).at(-1)?.searchParams.get("query")).toBe(
      "小黑",
    );
  });

  it("keeps the newest status response when an older filter returns late", async () => {
    let resolveActive!: (value: Response) => void;
    await renderPage({
      listHandler: (url) => {
        const requestedStatus = url.searchParams.get("status");
        if (requestedStatus === "active")
          return new Promise<Response>((resolve) => {
            resolveActive = resolve;
          });
        if (requestedStatus === "revoked")
          return response({
            items: [{ ...revokedQr, animal_name: "已撤銷新結果" }],
            page: 1,
            page_size: 20,
            total: 1,
          });
        return response({
          items: [activeQr],
          page: 1,
          page_size: 20,
          total: 1,
        });
      },
    });

    await changeControl("qr-status", "active");
    await changeControl("qr-status", "revoked");
    expect(recordNamed("已撤銷新結果")).toBeDefined();
    await act(async () => {
      resolveActive(
        response({
          items: [{ ...activeQr, animal_name: "過期使用中結果" }],
          page: 1,
          page_size: 20,
          total: 1,
        }),
      );
      await settle();
    });
    expect(recordNamed("已撤銷新結果")).toBeDefined();
    expect(recordNamed("過期使用中結果")).toBeUndefined();
  });

  it("keeps active data when the initial all-status response returns late", async () => {
    let resolveAll!: (value: Response) => void;
    const allRequest: { signal: AbortSignal | null } = { signal: null };
    await renderPage({
      listHandler: (url, init) => {
        if (url.searchParams.get("status") === "all") {
          allRequest.signal = init?.signal ?? null;
          return new Promise<Response>((resolve) => {
            resolveAll = resolve;
          });
        }
        return response({
          items: [{ ...activeQr, animal_name: "使用中目前結果" }],
          page: 1,
          page_size: 20,
          total: 1,
        });
      },
    });

    await changeControl("qr-status", "active");
    expect(recordNamed("使用中目前結果")).toBeDefined();
    expect(allRequest.signal?.aborted).toBe(true);

    await act(async () => {
      resolveAll(
        response({
          items: [{ ...revokedQr, animal_name: "過期全部結果" }],
          page: 1,
          page_size: 20,
          total: 1,
        }),
      );
      await settle();
    });
    expect(recordNamed("使用中目前結果")).toBeDefined();
    expect(recordNamed("過期全部結果")).toBeUndefined();
  });

  it("keeps page two when a late page-one request resolves", async () => {
    let holdPageOne = false;
    let resolvePageOne!: (value: Response) => void;
    await renderPage({
      listHandler: (url) => {
        const requestedPage = Number(url.searchParams.get("page"));
        if (requestedPage === 1 && holdPageOne)
          return new Promise<Response>((resolve) => {
            resolvePageOne = resolve;
          });
        return response({
          items: [
            {
              ...activeQr,
              animal_name:
                requestedPage === 1 ? "第一頁目前結果" : "第二頁目前結果",
            },
          ],
          page: requestedPage,
          page_size: 20,
          total: 21,
        });
      },
    });
    await clickButton("下一頁");
    holdPageOne = true;
    await clickButton("上一頁");
    await clickButton("下一頁");
    expect(recordNamed("第二頁目前結果")).toBeDefined();

    await act(async () => {
      resolvePageOne(
        response({
          items: [{ ...activeQr, animal_name: "過期第一頁結果" }],
          page: 1,
          page_size: 20,
          total: 21,
        }),
      );
      await settle();
    });
    expect(recordNamed("第二頁目前結果")).toBeDefined();
    expect(recordNamed("過期第一頁結果")).toBeUndefined();
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
