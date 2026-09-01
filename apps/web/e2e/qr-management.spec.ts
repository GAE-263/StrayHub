import { expect, test } from "@playwright/test";
import { mockManagementApi, type QrFixture } from "./fixtures";

function qrRecord(
  index: number,
  status: "active" | "revoked" = "active",
  organizationId = "org-a",
): QrFixture {
  return {
    id: `qr-${organizationId}-${index}`,
    organization_id: organizationId,
    animal_id: `animal-${organizationId}-${index}`,
    animal_name: `${organizationId === "org-a" ? "A舍" : "B舍"}動物 ${index}`,
    shelter_number: `${organizationId.toUpperCase()}-${String(index).padStart(3, "0")}`,
    animal_status: "active",
    area_name: index % 2 ? "犬舍 A 區" : "犬舍 B 區",
    status,
    revoked: status === "revoked",
    created_at: "2026-08-20T06:30:00Z",
    deep_link:
      status === "active"
        ? `https://example.test/qr/${organizationId}-${index}`
        : null,
    token: null,
  };
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
});

test("QR search and status filters use server results", async ({ page }) => {
  const records = [
    { ...qrRecord(1), animal_name: "小黑" },
    { ...qrRecord(2, "revoked"), animal_name: "阿福" },
  ];
  const requestedParams: Array<Record<string, string | null>> = [];
  await mockManagementApi(page, {
    qrCodes: (params) => {
      requestedParams.push({
        page: params.get("page"),
        pageSize: params.get("page_size"),
        query: params.get("query"),
        status: params.get("status"),
      });
      const query = params.get("query") ?? "";
      const status = params.get("status") ?? "all";
      const items = records.filter(
        (item) =>
          (status === "all" || item.status === status) &&
          (!query ||
            item.animal_name.includes(query) ||
            item.shelter_number?.includes(query)),
      );
      return { items, page: 1, page_size: 20, total: items.length };
    },
  });

  await page.goto("/settings/qr-codes");
  await expect(page.getByRole("link", { name: "小黑" })).toBeVisible();
  await expect(page.getByRole("link", { name: "阿福" })).toBeVisible();

  await page.getByLabel("搜尋").fill("小黑");
  await expect(page.getByRole("link", { name: "小黑" })).toBeVisible();
  await expect(page.getByRole("link", { name: "阿福" })).toHaveCount(0);
  expect(requestedParams).toContainEqual({
    page: "1",
    pageSize: "20",
    query: "小黑",
    status: "all",
  });

  await page.getByRole("button", { name: "重設篩選" }).click();
  await page.getByLabel("QR 狀態").selectOption("active");
  await expect(page.getByRole("link", { name: "小黑" })).toBeVisible();
  await expect(page.getByRole("link", { name: "阿福" })).toHaveCount(0);
  expect(requestedParams).toContainEqual({
    page: "1",
    pageSize: "20",
    query: null,
    status: "active",
  });

  await page.getByLabel("QR 狀態").selectOption("revoked");
  await expect(page.getByRole("link", { name: "阿福" })).toBeVisible();
  await expect(page.getByRole("link", { name: "小黑" })).toHaveCount(0);
  expect(requestedParams).toContainEqual({
    page: "1",
    pageSize: "20",
    query: null,
    status: "revoked",
  });
});

test("QR pagination requests and renders the second server page without mobile overflow", async ({
  page,
}) => {
  const records = Array.from({ length: 21 }, (_, index) => qrRecord(index + 1));
  const requestedParams: Array<Record<string, string | null>> = [];
  await mockManagementApi(page, {
    qrCodes: (params) => {
      const requestedPage = Number(params.get("page") ?? "1");
      requestedParams.push({
        page: params.get("page"),
        pageSize: params.get("page_size"),
        query: params.get("query"),
        status: params.get("status"),
      });
      const start = (requestedPage - 1) * 20;
      return {
        items: records.slice(start, start + 20),
        page: requestedPage,
        page_size: 20,
        total: records.length,
      };
    },
  });
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/settings/qr-codes");
  await expect(page.getByText("第 1 頁，共 21 筆")).toBeVisible();

  await page.getByRole("button", { name: "下一頁" }).click();
  await expect(page.getByRole("link", { name: "A舍動物 21" })).toBeVisible();
  await expect(page.getByText("第 2 頁，共 21 筆")).toBeVisible();
  expect(requestedParams).toContainEqual({
    page: "2",
    pageSize: "20",
    query: null,
    status: "all",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
});

test("late Org A QR response never publishes after switching to Org B", async ({
  page,
}) => {
  const organizations = ["a", "b"].map((suffix) => ({
    id: `org-${suffix}`,
    code: `ORG-${suffix.toUpperCase()}`,
    name: `Shelter ${suffix.toUpperCase()}`,
    role: "SHELTER_ADMIN",
    status: "active",
    timezone: "Asia/Taipei",
    timezone_version: 1,
  }));
  let heldAStarted = false;
  let releaseA!: (value: {
    items: QrFixture[];
    page: number;
    page_size: number;
    total: number;
  }) => void;
  await mockManagementApi(page, {
    organizations,
    platformRole: null,
    qrCodes: (params, organizationId) => {
      if (organizationId === "org-a" && params.get("query") === "hold") {
        heldAStarted = true;
        return new Promise((resolve) => {
          releaseA = resolve;
        });
      }
      const item = {
        ...qrRecord(1, "active", organizationId),
        animal_name: organizationId === "org-a" ? "Org A 動物" : "Org B 動物",
      };
      return { items: [item], page: 1, page_size: 20, total: 1 };
    },
  });

  await page.goto("/settings/qr-codes");
  await expect(page.getByRole("link", { name: "Org A 動物" })).toBeVisible();
  await page.getByLabel("搜尋").fill("hold");
  await expect.poll(() => heldAStarted).toBe(true);

  await page.getByLabel("切換目前收容所").selectOption("org-b");
  await expect(page).toHaveURL(/\/animals$/);
  await page.goto("/settings/qr-codes");
  await expect(page.getByRole("link", { name: "Org B 動物" })).toBeVisible();

  releaseA({
    items: [
      { ...qrRecord(9, "active", "org-a"), animal_name: "Org A 過期結果" },
    ],
    page: 1,
    page_size: 20,
    total: 1,
  });
  await page.waitForTimeout(100);
  await expect(page.getByRole("link", { name: "Org B 動物" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Org A 過期結果" })).toHaveCount(
    0,
  );
});
