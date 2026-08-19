import { test, expect } from "@playwright/test";
import { mockManagementApi } from "./fixtures";

test.describe("管理工作台 Shell", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() =>
      sessionStorage.setItem("access_token", "test-access"),
    );
    await mockManagementApi(page);
  });

  test("desktop can identify context and primary navigation", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "管理工作台總覽" }),
    ).toBeVisible();
    await expect(page.getByText("ORG-A")).toBeVisible();
    await expect(
      page.getByRole("link", { name: "動物檔案", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "可回報範圍", exact: true }),
    ).toHaveCount(0);
  });

  test("mobile exposes navigation through an accessible menu", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 578, height: 800 });
    await page.goto("/");
    const trigger = page.getByRole("button", { name: "開啟管理工作台導覽" });
    await expect(trigger).toBeVisible();
    await trigger.click();
    const sheet = page.getByRole("dialog", { name: "管理工作台導覽" });
    await expect(sheet).toBeVisible();
    const box = await sheet.boundingBox();
    expect(box).not.toBeNull();
    expect(box?.x).toBe(0);
    expect(box?.y).toBe(0);
    expect(box?.width).toBe(420);
    expect(box?.height).toBe(800);
    await expect(page.locator(".header-logout")).toBeHidden();
    await expect(
      sheet.getByRole("button", { name: "登出管理工作台" }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
  });

  test("tablet uses compact navigation without sidebar whitespace", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto("/");

    const trigger = page.getByRole("button", { name: "開啟管理工作台導覽" });
    await expect(trigger).toBeVisible();
    await expect(page.locator(".app-sidebar")).toBeHidden();
    await expect(page.locator(".header-logout")).toBeHidden();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);

    await trigger.click();
    await expect(
      page.getByRole("dialog", { name: "管理工作台導覽" }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
  });

  test("responsive shell follows the actual header height", async ({
    page,
  }) => {
    for (const viewport of [
      { width: 360, height: 800 },
      { width: 768, height: 1024 },
      { width: 1024, height: 768 },
    ]) {
      await page.setViewportSize(viewport);
      await page.goto("/");
      await expect(
        page.getByRole("heading", { name: "管理工作台總覽" }),
      ).toBeVisible();

      const geometry = await page.evaluate(() => {
        const frame = document.querySelector<HTMLElement>(".app-frame");
        const header = document.querySelector<HTMLElement>(".app-header");
        const body = document.querySelector<HTMLElement>(".app-body");
        if (!frame || !header || !body) throw new Error("app shell missing");
        const headerBox = header.getBoundingClientRect();
        const bodyBox = body.getBoundingClientRect();
        return {
          bodyMinHeight: getComputedStyle(body).minHeight,
          bodyTop: bodyBox.top,
          frameHeight: frame.getBoundingClientRect().height,
          headerBottom: headerBox.bottom,
          headerHeight: headerBox.height,
          horizontalOverflow:
            document.documentElement.scrollWidth > window.innerWidth,
        };
      });

      expect(geometry.bodyMinHeight).toBe("0px");
      expect(Math.abs(geometry.bodyTop - geometry.headerBottom)).toBeLessThan(
        1,
      );
      expect(geometry.frameHeight).toBeGreaterThanOrEqual(viewport.height);
      expect(geometry.horizontalOverflow).toBe(false);

      const trigger = page.getByRole("button", {
        name: "開啟管理工作台導覽",
      });
      if (viewport.width <= 900) {
        await expect(trigger).toBeVisible();
        await expect(page.locator(".app-sidebar")).toBeHidden();
        await expect(page.locator(".header-logout")).toBeHidden();
      } else {
        await expect(trigger).toBeHidden();
        await expect(page.locator(".app-sidebar")).toBeVisible();
        await expect(page.locator(".header-logout")).toBeVisible();
      }

      if (viewport.width === 360) {
        expect(geometry.headerHeight).toBeGreaterThan(72);
      }
    }
  });

  test("login and membership controls use the shared control height", async ({
    page,
  }) => {
    await page.goto("/login");
    await expect(
      page.getByRole("heading", { name: "浪浪森友會管理入口" }),
    ).toBeVisible();

    const loginHeights = await page
      .locator(".login-card input, .login-card button")
      .evaluateAll((elements) =>
        elements.map((element) =>
          Math.round(element.getBoundingClientRect().height),
        ),
      );
    expect(loginHeights).toEqual([44, 44, 44]);

    await page.goto("/shelters");
    await expect(page.locator(".shelter-management-page")).toBeVisible();
    const membershipHeights = await page
      .locator(".app-main input, .app-main select, .app-main button")
      .evaluateAll((elements) =>
        elements
          .filter(
            (element) => (element as HTMLInputElement).type !== "checkbox",
          )
          .map((element) => Math.round(element.getBoundingClientRect().height))
          .filter((height) => height > 0),
      );
    expect(membershipHeights.length).toBeGreaterThan(0);
    expect(new Set(membershipHeights)).toEqual(new Set([44]));
  });

  test("context switch failure is visible and logout returns to login", async ({
    page,
  }) => {
    await page.unroute("**/v1/**").catch(() => undefined);
    await mockManagementApi(page, {
      organizations: [
        {
          id: "org-a",
          code: "ORG-A",
          name: "浪浪森友會 A",
          role: "STAFF",
          status: "active",
          timezone: "Asia/Taipei",
          timezone_version: 1,
        },
        {
          id: "org-b",
          code: "ORG-B",
          name: "浪浪森友會 B",
          role: "STAFF",
          status: "active",
          timezone: "Asia/Taipei",
          timezone_version: 1,
        },
      ],
      contextSwitchStatus: 500,
    });
    await page.goto("/");
    await page.getByLabel("切換目前收容所").selectOption("org-b");
    await expect(page.getByText("無法切換目前收容所")).toBeVisible();
    await page.getByRole("button", { name: "登出管理工作台" }).click();
    await expect(page).toHaveURL(/\/login$/);
  });
});
