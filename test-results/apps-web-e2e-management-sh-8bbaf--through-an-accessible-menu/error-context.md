# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: apps/web/e2e/management-shell.spec.ts >> 管理工作台 Shell >> mobile exposes navigation through an accessible menu
- Location: apps/web/e2e/management-shell.spec.ts:23:7

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/", waiting until "load"

```

# Test source

```ts
  1  | import { test, expect } from "@playwright/test";
  2  | import { mockManagementApi } from "./fixtures";
  3  | 
  4  | test.describe("管理工作台 Shell", () => {
  5  |   test.beforeEach(async ({ page }) => {
  6  |     await page.addInitScript(() =>
  7  |       sessionStorage.setItem("access_token", "test-access"),
  8  |     );
  9  |     await mockManagementApi(page);
  10 |   });
  11 | 
  12 |   test("desktop can identify context and primary navigation", async ({
  13 |     page,
  14 |   }) => {
  15 |     await page.goto("/");
  16 |     await expect(
  17 |       page.getByRole("heading", { name: "管理工作台總覽" }),
  18 |     ).toBeVisible();
  19 |     await expect(page.getByText("ORG-A")).toBeVisible();
  20 |     await expect(page.getByRole("link", { name: "動物檔案" })).toBeVisible();
  21 |   });
  22 | 
  23 |   test("mobile exposes navigation through an accessible menu", async ({
  24 |     page,
  25 |   }) => {
  26 |     await page.setViewportSize({ width: 360, height: 800 });
> 27 |     await page.goto("/");
     |                ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  28 |     const trigger = page.getByRole("button", { name: "開啟管理工作台導覽" });
  29 |     await expect(trigger).toBeVisible();
  30 |     await trigger.click();
  31 |     await expect(
  32 |       page.getByRole("dialog", { name: "管理工作台導覽" }),
  33 |     ).toBeVisible();
  34 |     await page.keyboard.press("Escape");
  35 |     await expect(trigger).toBeFocused();
  36 |   });
  37 | });
  38 | 
```