import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockManagementApi } from "./fixtures";
import { mockVolunteerAccessApi } from "./volunteer-access-fixtures";

const viewports = [
  { width: 360, height: 800 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
];

const routes = [
  "/animals",
  "/animals/animal-a",
  "/animals/animal-a/timeline",
  "/reports",
  "/reports/report-a",
  "/animal-confirmation",
  "/care-report",
];

test("所有已登入 P0 route 在四個 viewport 沒有 critical 或 serious axe violations", async ({
  page,
}) => {
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "test-access"),
  );
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

test("志工報名與管理 routes 沒有 critical 或 serious axe violations", async ({
  page,
}) => {
  await mockVolunteerAccessApi(page);
  for (const route of [
    "/volunteer-application?entry=entry&id_token=id-token",
    "/volunteers/applications",
    "/volunteers/access",
    "/volunteers/notifications",
    "/settings/volunteer-access",
  ]) {
    await page.goto(route);
    await expect(page.locator("main").first()).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(
      results.violations.filter((item) =>
        ["critical", "serious"].includes(item.impact ?? ""),
      ),
      route,
    ).toEqual([]);
  }
});
