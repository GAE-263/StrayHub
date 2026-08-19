import { test, expect } from "@playwright/test";
import { mockManagementApi } from "./fixtures";

test.describe("管理工作台 Shell", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() =>
      sessionStorage.setItem("access_token", "test-access"),
    );
    await mockManagementApi(page);
  });

  test("desktop can identify context and primary navigation", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "管理工作台總覽" }),
    ).toBeVisible();
    await expect(page.getByText("ORG-A")).toBeVisible();
    await expect(
      page.getByRole("link", { name: "動物檔案", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "可回報範圍", exact: true }),
    ).toHaveCount(0);
  });

  test("mobile exposes navigation through an accessible menu", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 578, height: 800 });
    await page.goto("/");
    const trigger = page.getByRole("button", { name: "開啟管理工作台導覽" });
    await expect(trigger).toBeVisible();
    await trigger.click();
    const sheet = page.getByRole("dialog", { name: "管理工作台導覽" });
    await expect(sheet).toBeVisible();
    const box = await sheet.boundingBox();
    expect(box).not.toBeNull();
    expect(box?.x).toBe(0);
    expect(box?.y).toBe(0);
    expect(box?.width).toBe(420);
    expect(box?.height).toBe(800);
    await expect(page.locator(".header-logout")).toBeHidden();
    await expect(
      sheet.getByRole("button", { name: "登出管理工作台" }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
  });

  test("context switch failure is visible and logout returns to login", async ({
    page,
  }) => {
    await page.unroute("**/v1/**").catch(() => undefined);
    await mockManagementApi(page, {
      organizations: [
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
      ],
      contextSwitchStatus: 500,
    });
    await page.goto("/");
    await page.getByLabel("切換目前收容所").selectOption("org-b");
    await expect(
      page.getByText("無法切換 Active Shelter Context"),
    ).toBeVisible();
    await page.getByRole("button", { name: "登出管理工作台" }).click();
    await expect(page).toHaveURL(/\/login$/);
  });
});
