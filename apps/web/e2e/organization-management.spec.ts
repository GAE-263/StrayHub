import { expect, test, type Page } from "@playwright/test";

async function mockOrganizationManagement(page: Page, role: string) {
  let archived = true;
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
    if (url.pathname.endsWith("/memberships/archived")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: archived
            ? [
                {
                  id: "membership-archived",
                  organization_id: "org-a",
                  user_id: "archived-user",
                  username: "archived-staff",
                  display_name: "已封存工作人員",
                  role: "STAFF",
                  status: "archived",
                  access_version: 1,
                  archived_from_status: "disabled",
                },
              ]
            : [],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/restore")) {
      archived = false;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "membership-archived",
          organization_id: "org-a",
          user_id: "archived-user",
          username: "archived-staff",
          display_name: "已封存工作人員",
          role: "STAFF",
          status: "disabled",
          access_version: 2,
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
        body: JSON.stringify({
          items: url.pathname.endsWith("/memberships")
            ? [
                {
                  id: "membership-admin",
                  organization_id: "org-a",
                  user_id: "admin-id",
                  username: "local-admin-a",
                  display_name: "本機管理員 A",
                  role: "SHELTER_ADMIN",
                  status: "active",
                  access_version: 1,
                  medical_care_access: false,
                },
                {
                  id: "membership-staff",
                  organization_id: "org-a",
                  user_id: "staff-id",
                  username: "local-staff-a",
                  display_name: "本機工作人員 A",
                  role: "STAFF",
                  status: "disabled",
                  access_version: 1,
                  medical_care_access: false,
                },
                {
                  id: "membership-volunteer",
                  organization_id: "org-a",
                  user_id: "volunteer-id",
                  username: "local-volunteer-a",
                  display_name: "本機志工 A",
                  role: "VOLUNTEER",
                  status: "disabled",
                  access_version: 1,
                  medical_care_access: false,
                  volunteer_authorization_status: "revoked",
                },
              ]
            : [],
        }),
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
  await expect(page.getByRole("heading", { name: "權限管理" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "建立收容所" })).toBeVisible();
  await page.getByLabel("機構代碼").fill("ORG-NEW");
  await page.getByLabel("收容所名稱").fill("新收容所");
  await page.getByLabel("初始管理員帳號").fill("local-shelter-admin-a");
  await page.getByLabel("初始管理員暫時密碼").fill("temporary-password");
  await page.getByRole("button", { name: "建立收容所" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "收容所已建立" }),
  ).toBeVisible();
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
  await expect(page.getByRole("heading", { name: "權限管理" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "帳號與權限" })).toBeVisible();
  await expect(page.getByText("本機工作人員 A")).toBeVisible();
  await expect(page.getByText("帳號：local-staff-a")).toBeVisible();
  await expect(page.getByText("時區")).toHaveCount(0);
  await expect(page.getByLabel("收容所時區")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "儲存時區" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "建立收容所" })).toHaveCount(
    0,
  );
  await expect(page.getByRole("heading", { name: "志工" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "工作人員" })).toBeVisible();
  await expect(page.getByText("授權已撤銷")).toBeVisible();
  await page.getByRole("button", { name: "建立帳號" }).click();
  await expect(
    page.getByRole("heading", { name: "建立機構帳號" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "取消" }).click();
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

test("SHELTER_ADMIN 可在已封存路由查詢並恢復成員", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "test-access"),
  );
  await mockOrganizationManagement(page, "SHELTER_ADMIN");
  await page.goto("/shelters/archived");
  await expect(page.getByRole("heading", { name: "已封存成員" })).toBeVisible();
  await expect(page.getByText("已封存工作人員")).toBeVisible();
  await expect(page.getByText("封存前：已停用")).toBeVisible();
  await page.getByRole("button", { name: "恢復成員" }).click();
  await page.getByRole("button", { name: "確認調整" }).click();
  const toast = page.getByRole("status").filter({ hasText: "已恢復成員" });
  await expect(toast).toBeVisible();
  const toastBox = await toast.boundingBox();
  expect(toastBox).not.toBeNull();
  expect((toastBox?.x ?? 0) + (toastBox?.width ?? 0)).toBeLessThanOrEqual(360);
  await toast.screenshot({ path: testInfo.outputPath("ft018-toast-360.png") });
  await toast.getByRole("button", { name: "關閉通知" }).click();
  await expect(toast).toHaveCount(0);
  await expect(
    page.getByText("目前沒有符合條件的封存工作人員。"),
  ).toBeVisible();
});
