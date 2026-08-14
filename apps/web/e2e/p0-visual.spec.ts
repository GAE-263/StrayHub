import { test, expect } from "@playwright/test";
import { mockManagementApi } from "./fixtures";

const viewports = [
  { width: 360, height: 800 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
];

const routes = [
  "/login",
  "/",
  "/animals",
  "/animals/animal-a",
  "/animals/animal-a/timeline",
  "/reports",
  "/reports/report-a",
  "/animal-confirmation",
  "/care-report",
];

for (const route of routes) {
  const slug = route === "/" ? "home" : route.slice(1).replaceAll("/", "-");
  test(`${route} 建立 P0 visual evidence`, async ({ page }) => {
    await page.addInitScript(() =>
      sessionStorage.setItem("access_token", "test-access"),
    );
    await mockManagementApi(page);
    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      await page.goto(route);
      await expect(page.locator("main").first()).toBeVisible();
      await expect(page).toHaveScreenshot(`${slug}-${viewport.width}.png`, {
        fullPage: true,
      });
    }
  });
}
