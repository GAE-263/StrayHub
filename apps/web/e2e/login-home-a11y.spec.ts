import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockManagementApi } from "./fixtures";

const viewports = [
  { width: 360, height: 800 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
];

for (const viewport of viewports) {
  test(`/login ${viewport.width}x${viewport.height} 通過 axe 與表單語意檢查`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto("/login");
    await expect(page.getByLabel("帳號")).toBeVisible();
    await expect(page.getByLabel("密碼")).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(
      results.violations.filter((item) =>
        ["critical", "serious"].includes(item.impact ?? ""),
      ),
    ).toEqual([]);
  });

  test(`/ 管理首頁 ${viewport.width}x${viewport.height} 通過 axe 與狀態語意檢查`, async ({
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
    const results = await new AxeBuilder({ page }).analyze();
    expect(
      results.violations.filter((item) =>
        ["critical", "serious"].includes(item.impact ?? ""),
      ),
    ).toEqual([]);
  });
}
