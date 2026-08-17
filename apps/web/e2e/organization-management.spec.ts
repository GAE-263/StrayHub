import { expect, test, type Page } from "@playwright/test";

async function mockOrganizationManagement(page: Page, role: string) {
  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/auth/me")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user: {
            id: "user-a",
            username:
              role === "PLATFORM_ADMIN" ? "platform-admin" : "shelter-admin",
            display_name: "測試使用者",
            platform_role: role === "PLATFORM_ADMIN" ? role : null,
            status: "active",
          },
          memberships: [
            {
              id: "membership-a",
              organization_id: "org-a",
              role,
              status: "active",
            },
          ],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/auth/active-shelter-context")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ organization_id: "org-a" }),
      });
      return;
    }
    if (url.pathname === "/v1/organizations") {
      if (route.request().method() === "POST") {
        if (role !== "PLATFORM_ADMIN") {
          await route.fulfill({
            status: 403,
            contentType: "application/json",
            body: JSON.stringify({
              code: "platform_admin_required",
              message: "需要平台管理員權限",
            }),
          });
          return;
        }
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify({
            id: "org-new",
            code: "ORG-NEW",
            name: "新收容所",
            status: "pending_setup",
            timezone: "Asia/Taipei",
            timezone_version: 1,
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              id: "org-a",
              code: "ORG-A",
              name: "浪浪森友會 A",
              status: "active",
              timezone: "Asia/Taipei",
              timezone_version: 1,
            },
          ],
        }),
      });
      return;
    }
    if (url.pathname === "/v1/management/audit") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              action: "organization.created",
              result: "success",
              resource_type: "organization",
            },
          ],
        }),
      });
      return;
    }
    if (
      url.pathname.endsWith("/memberships") ||
      url.pathname.endsWith("/areas")
    ) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [] }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    });
  });
}

test("PLATFORM_ADMIN 可看到建立收容所表單", async ({ page }) => {
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "test-access"),
  );
  await mockOrganizationManagement(page, "PLATFORM_ADMIN");
  await page.goto("/shelters");
  await expect(
    page.getByRole("heading", { name: "收容所與帳號管理" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "建立收容所" })).toBeVisible();
  await page.getByLabel("機構代碼").fill("ORG-NEW");
  await page.getByLabel("收容所名稱").fill("新收容所");
  await page.getByLabel("初始管理員帳號").fill("local-shelter-admin-a");
  await page.getByLabel("初始管理員暫時密碼").fill("temporary-password");
  await page.getByRole("button", { name: "建立收容所" }).click();
  await expect(page.getByRole("status")).toContainText("收容所已建立");
  const audit = await page.evaluate(async () => {
    const response = await fetch(
      "/v1/management/audit?resource_type=organization",
    );
    return response.json();
  });
  expect(audit.items[0].action).toBe("organization.created");
});

test("SHELTER_ADMIN 只能管理目前收容所設定", async ({ page }) => {
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "test-access"),
  );
  await mockOrganizationManagement(page, "SHELTER_ADMIN");
  await page.goto("/shelters");
  await expect(page.getByText("照護日期與時區")).toBeVisible();
  await expect(page.getByText("帳號與 Membership")).toBeVisible();
  await expect(page.getByRole("heading", { name: "建立收容所" })).toHaveCount(
    0,
  );
  const denied = await page.evaluate(async () => {
    const response = await fetch("/v1/organizations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: "SHOULD-NOT-CREATE",
        name: "不應建立",
        status: "pending_setup",
        initial_admin_username: "local-shelter-admin-a",
        initial_admin_temporary_password: "temporary-password",
      }),
    });
    return { status: response.status, body: await response.json() };
  });
  expect(denied.status).toBe(403);
  expect(denied.body.code).toBe("platform_admin_required");
});
