# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: apps/web/e2e/login-home.spec.ts >> login form exposes labels and saving state
- Location: apps/web/e2e/login-home.spec.ts:4:5

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/login", waiting until "load"

```

# Test source

```ts
  1  | import { test, expect } from "@playwright/test";
  2  | import { mockLoginApi } from "./fixtures";
  3  | 
  4  | test("login form exposes labels and saving state", async ({ page }) => {
  5  |   await mockLoginApi(page);
> 6  |   await page.goto("/login");
     |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  7  |   await expect(
  8  |     page.getByRole("heading", { name: "浪浪森友會管理入口" }),
  9  |   ).toBeVisible();
  10 |   await expect(page.getByLabel("帳號")).toHaveValue("local-staff-a");
  11 |   await page.getByRole("button", { name: "登入" }).click();
  12 |   await expect(page).toHaveURL(/\/$/);
  13 | });
  14 | 
```