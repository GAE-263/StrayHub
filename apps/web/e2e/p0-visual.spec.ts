import { test, expect } from "@playwright/test";
import { mockManagementApi } from "./fixtures";
import { mockVolunteerAccessApi } from "./volunteer-access-fixtures";

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

const volunteerRoutes = [
  "/volunteer-application?entry=entry&id_token=id-token",
  "/volunteers/applications",
  "/settings/volunteer-access",
  "/volunteers/access",
  "/volunteers/notifications",
];

for (const route of volunteerRoutes) {
  const slug = route.split("?")[0].slice(1).replaceAll("/", "-");
  test(`${route} 建立志工授權 visual evidence`, async ({ page }) => {
    test.skip(
      process.env.VOLUNTEER_ACCESS_VISUAL_REVIEW !== "approved",
      "等待 reviewer 確認志工授權 UI 後建立 baseline",
    );
    await mockVolunteerAccessApi(page);
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

test("志工批次確認、進度與 partial result 建立 visual evidence", async ({
  page,
}) => {
  test.skip(
    process.env.VOLUNTEER_ACCESS_VISUAL_REVIEW !== "approved",
    "等待 reviewer 確認志工授權 UI 後建立 baseline",
  );
  await mockVolunteerAccessApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/volunteers/applications");
  await page.getByRole("checkbox", { name: /目前篩選結果全部/ }).check();
  await page.getByRole("button", { name: "確認並建立批次" }).click();
  await expect(page).toHaveScreenshot("volunteer-batch-confirmation.png", {
    fullPage: true,
  });
  await page.getByRole("button", { name: "送出完整快照" }).click();
  await expect(page.getByText("批次已建立")).toBeVisible();
  await expect(page).toHaveScreenshot("volunteer-batch-partial-result.png", {
    fullPage: true,
  });
});
