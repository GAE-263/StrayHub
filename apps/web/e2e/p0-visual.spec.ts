import { test, expect, type Page } from "@playwright/test";
import { mockManagementApi } from "./fixtures";
import { mockGovernanceVisualApi } from "./governance-visual-fixtures";
import {
  mockLiffBrowser,
  mockVolunteerAccessApi,
} from "./volunteer-access-fixtures";

async function mockVolunteerEntryNew(
  page: Parameters<typeof mockLiffBrowser>[0],
) {
  await page.route("**/v1/auth/liff/exchange", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        state: "NEW",
        organization: {
          id: "org-a",
          code: "ORG-A",
          name: "收容所 A",
        },
        user: { role: "VOLUNTEER" },
      }),
    });
  });
  await mockLiffBrowser(page);
}

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
  "/care-calendar",
  "/reports",
  "/reports/report-a",
  "/animal-confirmation",
  "/care-report",
];

async function expectNoDevIndicator(page: Page) {
  await expect(page.locator("nextjs-portal")).toBeHidden();
}

test("visual runtime excludes the Next.js dev indicator", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator("main").first()).toBeVisible();
  await expectNoDevIndicator(page);
});

for (const route of routes) {
  const slug = route === "/" ? "home" : route.slice(1).replaceAll("/", "-");
  for (const viewport of viewports) {
    test(`${route} @ ${viewport.width}x${viewport.height} 建立 P0 visual evidence`, async ({
      page,
    }) => {
      await page.addInitScript(() =>
        sessionStorage.setItem("access_token", "test-access"),
      );
      await mockManagementApi(page);
      await page.setViewportSize(viewport);
      await page.goto(route);
      await expect(page.locator("main").first()).toBeVisible();
      await expectNoDevIndicator(page);
      await expect(page).toHaveScreenshot(`${slug}-${viewport.width}.png`, {
        fullPage: true,
      });
    });
  }
}

const governanceRoutes = [
  "/shelters",
  "/shelters/archived",
  "/platform-admins",
];

for (const route of governanceRoutes) {
  const slug = route.slice(1).replaceAll("/", "-");
  for (const viewport of viewports) {
    test(`${route} @ ${viewport.width}x${viewport.height} 建立治理 visual evidence`, async ({
      page,
    }) => {
      await mockGovernanceVisualApi(page);
      await page.setViewportSize(viewport);
      await page.goto(route);
      await expect(page.locator("main").first()).toBeVisible();
      await expectNoDevIndicator(page);
      await expect(page).toHaveScreenshot(`${slug}-${viewport.width}.png`, {
        fullPage: true,
      });
    });
  }
}

const volunteerRoutes = [
  "/volunteer-entry?entry=opaque-entry-reference-0123456789abcdef-extra",
  "/volunteers/applications",
  "/settings/volunteer-access",
  "/volunteers/access",
  "/volunteers/notifications",
];

for (const route of volunteerRoutes) {
  const slug = route.split("?")[0].slice(1).replaceAll("/", "-");
  for (const viewport of viewports) {
    test(`${route} @ ${viewport.width}x${viewport.height} 建立志工授權 visual evidence`, async ({
      page,
    }) => {
      if (route.startsWith("/volunteer-entry")) {
        await mockVolunteerEntryNew(page);
      } else {
        await mockVolunteerAccessApi(page);
      }
      await page.setViewportSize(viewport);
      await page.goto(route);
      await expect(page.locator("main").first()).toBeVisible();
      await expectNoDevIndicator(page);
      await expect(page).toHaveScreenshot(`${slug}-${viewport.width}.png`, {
        fullPage: true,
      });
    });
  }
}

for (const viewport of viewports) {
  test(`志工批次確認與 partial result @ ${viewport.width}x${viewport.height} 建立 visual evidence`, async ({
    page,
  }) => {
    await mockVolunteerAccessApi(page);
    await page.setViewportSize(viewport);
    await page.goto("/volunteers/applications");
    await page.getByRole("checkbox", { name: /目前篩選結果全部/ }).check();
    await page.getByRole("button", { name: "確認並建立批次" }).click();
    await expectNoDevIndicator(page);
    await expect(page.getByRole("alertdialog")).toHaveScreenshot(
      `volunteer-batch-confirmation-${viewport.width}.png`,
    );
    await page.getByRole("button", { name: "送出完整快照" }).click();
    await expect(page.getByText("批次已建立")).toBeVisible();
    await page
      .getByRole("heading", { name: "逐筆結果" })
      .scrollIntoViewIfNeeded();
    await expectNoDevIndicator(page);
    await expect(page).toHaveScreenshot(
      `volunteer-batch-partial-result-${viewport.width}.png`,
      { fullPage: false },
    );
  });
}
