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
  for (const viewport of viewports) {
    test(`${route} 在 ${viewport.width}x${viewport.height} 不產生核心水平溢出`, async ({
      page,
    }) => {
      await page.setViewportSize(viewport);
      await page.addInitScript(() =>
        sessionStorage.setItem("access_token", "test-access"),
      );
      await mockManagementApi(page);
      await page.goto(route);
      await expect(page.locator("main").first()).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth + 1,
        ),
      ).toBe(true);
    });
  }
}

test("P0 routes respect reduced-motion preference", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/login");
  const reducedMotion = await page.evaluate(() => ({
    mediaMatches: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    stylesheetRulePresent: Array.from(document.styleSheets).some((sheet) => {
      try {
        return Array.from(sheet.cssRules).some((rule) =>
          rule.cssText.includes("prefers-reduced-motion"),
        );
      } catch {
        return false;
      }
    }),
  }));
  expect(reducedMotion).toEqual({
    mediaMatches: true,
    stylesheetRulePresent: true,
  });
});
