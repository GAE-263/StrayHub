import { test, expect } from "@playwright/test";
import { mockManagementApi } from "./fixtures";

const p1Routes = [
  ["/ai-review", "AI Review Queue"],
  ["/shelters", "收容所與帳號管理"],
  ["/settings/observation-options", "觀察詞彙"],
  ["/settings/qr-codes", "QR 綁定"],
  ["/settings/reportable-scope", "可回報範圍"],
  ["/settings/audit", "Audit Query"],
] as const;

test.describe("P1 management routes", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      sessionStorage.setItem("access_token", "test-access");
      sessionStorage.setItem("active_organization_id", "org-a");
    });
    await mockManagementApi(page);
  });

  test("AI Review、Shelter 與 Settings routes 保留主要 state 與資料邊界", async ({
    page,
  }) => {
    for (const [route, heading] of p1Routes) {
      await page.goto(route);
      await expect(page.locator("main").first()).toBeVisible();
      await expect(
        page.getByRole("heading", { name: heading, exact: true }),
      ).toBeVisible();
    }

    await page.goto("/ai-review");
    await expect(page.getByText("需要人工覆核")).toBeVisible();
    await expect(page.getByRole("link", { name: "查看來源" })).toHaveAttribute(
      "href",
      "/reports/report-a",
    );

    await page.goto("/settings/observation-options");
    await page.getByRole("button", { name: /情緒/ }).click();
    await page.getByRole("button", { name: /平台預設/ }).click();
    await expect(page.getByText("平靜")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "平台預設與收容所自訂", exact: true }),
    ).toBeVisible();

    await page.goto("/settings/qr-codes");
    await expect(page.getByText("目前沒有 QR 綁定。")).toHaveCount(0);
    await expect(page.getByText("active", { exact: true })).toBeVisible();

    await page.goto("/settings/reportable-scope");
    await expect(page.getByText("Animal animal-a")).toBeVisible();

    await page.goto("/settings/audit");
    await expect(page.getByText("observation_option.created")).toBeVisible();

    await page.goto("/shelters");
    await expect(page.getByText("帳號與 Membership")).toBeVisible();
    await expect(page.getByText("Cage / Area")).toBeVisible();
  });

  test("AI Queue permission denied 顯示繁中下一步且不渲染資料", async ({
    page,
  }) => {
    await page.route("**/v1/management/ai-review?*", async (route) => {
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: JSON.stringify({ message: "目前角色無權限查看 AI Queue" }),
      });
    });
    await page.goto("/ai-review");
    await expect(
      page.getByRole("alert").filter({ hasText: "無法載入 AI Queue" }),
    ).toBeVisible();
    await expect(page.getByText("需要人工覆核")).toHaveCount(0);
  });
});
