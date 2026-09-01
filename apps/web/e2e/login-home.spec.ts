import { test, expect } from "@playwright/test";
import { mockLoginApi, mockManagementApi } from "./fixtures";

const viewports = [
  { width: 360, height: 800 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
];

for (const viewport of viewports) {
  test(`/login 在 ${viewport.width}x${viewport.height} 可完成登入`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await mockLoginApi(page);
    await page.goto("/login");
    await expect(
      page.getByRole("heading", { name: "浪浪森友會管理入口" }),
    ).toBeVisible();
    await expect(page.getByLabel("帳號")).toHaveValue("demo-furkids-admin");
    await page.getByRole("button", { name: "登入" }).click();
    await expect(page).toHaveURL(/\/$/);
  });

  test(`/ 管理首頁在 ${viewport.width}x${viewport.height} 顯示摘要與入口`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.addInitScript(() =>
      sessionStorage.setItem("access_token", "test-access"),
    );
    await mockManagementApi(page);
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "管理工作台總覽" }),
    ).toBeVisible();
    await expect(page.getByText("目前沒有最近回報")).toBeVisible();
    await expect(
      page.getByRole("link", { name: "查看動物清單" }),
    ).toBeVisible();
  });
}

test("登入後可選擇多收容所 Active Shelter Context", async ({ page }) => {
  await mockLoginApi(page, [
    {
      id: "org-a",
      code: "ORG-A",
      name: "浪浪森友會 A",
      role: "STAFF",
      status: "active",
      timezone: "Asia/Taipei",
      timezone_version: 1,
    },
    {
      id: "org-b",
      code: "ORG-B",
      name: "浪浪森友會 B",
      role: "STAFF",
      status: "active",
      timezone: "Asia/Taipei",
      timezone_version: 1,
    },
  ]);
  await page.goto("/login");
  await page.getByRole("button", { name: "登入" }).click();
  await expect(
    page.getByRole("heading", { name: "確認目前收容所" }),
  ).toBeVisible();
  await expect(page.getByLabel("目前收容所", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "進入管理工作台" }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("tenantless PLATFORM_ADMIN 可登入平台治理", async ({ page }) => {
  await mockLoginApi(page, {
    organizations: [],
    platformRole: "PLATFORM_ADMIN",
  });
  await page.goto("/login");
  await page.getByRole("button", { name: "登入" }).click();
  await expect(page).toHaveURL(/\/platform-admins$/);
});
