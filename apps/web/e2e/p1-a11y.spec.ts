import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockManagementApi } from "./fixtures";

const viewports = [
  { width: 360, height: 800 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
];

const routes = [
  "/ai-review",
  "/shelters",
  "/settings/observation-options",
  "/settings/qr-codes",
  "/settings/reportable-scope",
  "/settings/audit",
];

test("P1 management routes 在四個 viewport 沒有 critical 或 serious axe violations", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  await mockManagementApi(page);

  for (const route of routes) {
    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      await page.goto(route);
      await expect(page.locator("main").first()).toBeVisible();
      const results = await new AxeBuilder({ page }).analyze();
      expect(
        results.violations.filter((item) =>
          ["critical", "serious"].includes(item.impact ?? ""),
        ),
        `${route} ${viewport.width}x${viewport.height}`,
      ).toEqual([]);
    }
  }
});
