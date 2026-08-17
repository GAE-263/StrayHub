import { test, expect } from "@playwright/test";
import { mockVolunteerApi } from "./fixtures";

test("志工可找到並確認動物", async ({ page }) => {
  await mockVolunteerApi(page);
  await page.goto("/animal-confirmation");
  await expect(
    page.getByRole("heading", { name: "選擇照護動物" }),
  ).toBeVisible();
  await expect(page.getByText("小森／A-001")).toBeVisible();
  await page.getByRole("button", { name: "查看確認卡" }).click();
  await expect(
    page.getByRole("heading", { name: "請確認回報對象" }),
  ).toBeVisible();
});

test("志工照護回報保留草稿內容", async ({ page }) => {
  await mockVolunteerApi(page);
  await page.goto("/care-report");
  await expect(
    page.getByRole("heading", { name: "照護回報備援介面" }),
  ).toBeVisible();
  await expect(page.getByText("目前步驟：care")).toBeVisible();
});
