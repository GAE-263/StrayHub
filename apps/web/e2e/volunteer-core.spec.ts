import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
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
  await expect(page.locator("[id='animal-confirmation-title']")).toHaveCount(1);
  await expect(
    page.locator("[id='animal-confirmation-card-title']"),
  ).toHaveCount(1);
  const results = await new AxeBuilder({ page }).analyze();
  expect(
    results.violations.filter((item) =>
      ["critical", "serious"].includes(item.impact ?? ""),
    ),
  ).toEqual([]);
});

test("動物確認頁在手機與平板使用一致的志工 shell", async ({
  page,
}, testInfo) => {
  await mockVolunteerApi(page);

  for (const viewport of [
    { width: 360, height: 800, columns: 1 },
    { width: 768, height: 1024, columns: 2 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/animal-confirmation");
    const shell = page.locator("main.volunteer-page");
    await expect(shell).toBeVisible();
    await expect(page.locator(".volunteer-search-card.ui-card")).toHaveCount(2);
    const geometry = await page.evaluate(() => {
      const pageShell = document.querySelector<HTMLElement>(".volunteer-page");
      const grid = document.querySelector<HTMLElement>(
        ".volunteer-search-grid",
      );
      return {
        columns: getComputedStyle(grid!).gridTemplateColumns.split(" ").length,
        pageWidth: pageShell!.getBoundingClientRect().width,
        viewportWidth: window.innerWidth,
        overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      };
    });
    expect(geometry.columns).toBe(viewport.columns);
    expect(geometry.pageWidth).toBeLessThanOrEqual(960);
    expect(geometry.pageWidth).toBeLessThanOrEqual(geometry.viewportWidth);
    expect(geometry.overflow).toBe(false);
    await page.locator("nextjs-portal").evaluateAll((portals) => {
      portals.forEach((portal) => {
        (portal as HTMLElement).style.display = "none";
      });
    });
    await page.screenshot({
      path: testInfo.outputPath(`ft019-after-${viewport.width}.png`),
      fullPage: true,
    });
    await page.getByRole("button", { name: "查看確認卡" }).click();
    await expect(page.locator(".animal-confirmation-card")).toBeVisible();
    const confirmationColumns = await page
      .locator(".animal-confirmation-layout")
      .evaluate(
        (element) =>
          getComputedStyle(element).gridTemplateColumns.split(" ").length,
      );
    expect(confirmationColumns).toBe(viewport.columns);
    await page.screenshot({
      path: testInfo.outputPath(`ft021-animal-card-${viewport.width}.png`),
      fullPage: true,
    });
  }
});

test("志工照護回報保留草稿內容", async ({ page }, testInfo) => {
  await mockVolunteerApi(page);
  for (const viewport of [
    { width: 360, height: 800 },
    { width: 768, height: 1024 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/care-report");
    await expect(
      page.getByRole("heading", { name: "照護回報備援介面" }),
    ).toBeVisible();
    await expect(page.getByText("目前步驟：care")).toBeVisible();
    await page.locator("nextjs-portal").evaluateAll((portals) => {
      portals.forEach((portal) => {
        (portal as HTMLElement).style.display = "none";
      });
    });
    await page.screenshot({
      path: testInfo.outputPath(`ft021-report-card-${viewport.width}.png`),
      fullPage: true,
    });
  }
});
