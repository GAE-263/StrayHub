import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("browser tooling launches Chromium and axe", async ({ page }) => {
  await page.setContent(
    '<main><h1>工具鏈檢查</h1><button type="button">確認</button></main>',
  );
  await expect(page.getByRole("heading", { name: "工具鏈檢查" })).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(Array.isArray(results.violations)).toBe(true);
});
