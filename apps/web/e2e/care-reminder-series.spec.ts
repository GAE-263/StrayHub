import { expect, test } from "@playwright/test";
import { mockManagementApi } from "./fixtures";

test("管理員可建立每月提醒並送出週期欄位", async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  let payload: Record<string, unknown> | null = null;
  await mockManagementApi(page, { timelines: () => ({ days: [] }) });
  await page.route(
    "**/v1/management/animals/animal-a/care-reminder-series",
    async (route) => {
      payload = JSON.parse(route.request().postData() ?? "{}");
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ id: "series-1", ...payload }),
      });
    },
  );
  await page.goto("/animals/animal-a");
  await page.getByRole("button", { name: "建立提醒" }).click();
  await page.getByLabel("提醒類型").selectOption("medication");
  await page.getByLabel("標題").fill("每月預防藥");
  await page.getByLabel("第一次執行").fill("2026-08-31T09:00");
  await page.getByLabel("重複週期").selectOption("monthly");
  await page.getByLabel("間隔").fill("1");
  await page
    .locator("form")
    .evaluate((form) => (form as HTMLFormElement).requestSubmit());
  await expect
    .poll(() => payload)
    .toMatchObject({ title: "每月預防藥", frequency: "monthly", interval: 1 });
});

test("提醒表單可設定每三個月並保留短月 anchor", async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  let payload: Record<string, unknown> | null = null;
  await mockManagementApi(page, { timelines: () => ({ days: [] }) });
  await page.route(
    "**/v1/management/animals/animal-a/care-reminder-series",
    async (route) => {
      payload = JSON.parse(route.request().postData() ?? "{}");
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ id: "series-3", ...payload }),
      });
    },
  );
  await page.goto("/animals/animal-a");
  await page.getByRole("button", { name: "建立提醒" }).click();
  await page.getByRole("textbox", { name: "標題" }).fill("每季量體重");
  await page.getByLabel("第一次執行").fill("2026-08-31T09:00");
  await page.getByLabel("重複週期").selectOption("monthly");
  await page.getByLabel("間隔").fill("3");
  await page
    .locator("form")
    .evaluate((form) => (form as HTMLFormElement).requestSubmit());
  await expect
    .poll(() => payload)
    .toMatchObject({ title: "每季量體重", frequency: "monthly", interval: 3 });
});
