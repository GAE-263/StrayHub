import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockManagementApi } from "./fixtures";

const org = "00000000-0000-4000-8000-000000000001";
const user = "00000000-0000-4000-8000-000000000002";
const profile = (password = false, organizations: unknown[] = []) => ({
  user: {
    id: user,
    display_name: "林小森",
    username: password ? "lin.sen" : null,
    platform_role: null,
  },
  state: organizations.length ? "ready" : "account_only",
  organizations,
  login_methods: { google: !password, password },
});
async function assertAccessible(page: Page) {
  const result = await new AxeBuilder({ page }).analyze();
  expect(
    result.violations.filter((item) =>
      ["critical", "serious"].includes(item.impact ?? ""),
    ),
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
}
async function capture(page: Page, name: string) {
  // Only synthetic fixtures are present in these review artifacts.
  await page.screenshot({
    path: `/tmp/strayhub-identity-${name}.png`,
    fullPage: true,
  });
}
async function loginMock(page: Page) {
  await page.addInitScript(() => {
    // GIS remains externally owned; this mock exercises our surrounding UX only.
    (window as unknown as { google: unknown }).google = {
      accounts: {
        id: {
          initialize: () => {},
          renderButton: (element: HTMLElement) => {
            const button = document.createElement("button");
            button.textContent = "使用 Google 帳號登入";
            button.style.cssText =
              "width:100%;min-height:44px;background:white;border:1px solid #747775;border-radius:24px;color:#1f1f1f;font-size:14px;padding:10px 24px";
            element.appendChild(button);
          },
        },
      },
    };
  });
  await page.route("**/v1/auth/google/config", (route) =>
    route.fulfill({ json: { enabled: true } }),
  );
  await page.route("**/v1/auth/google/transactions", (route) =>
    route.fulfill({
      json: {
        transaction_id: "test",
        nonce: "nonce",
        csrf_token: "csrf",
        client_id: "synthetic",
      },
    }),
  );
}
for (const width of [360, 1440]) {
  test(`登入、首次註冊 ${width}px 可閱讀並支援鍵盤`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await loginMock(page);
    await page.goto("/login");
    await expect(
      page.getByRole("button", { name: "使用 Google 帳號登入" }),
    ).toBeVisible();
    await expect(page.getByLabel("密碼", { exact: true })).toBeHidden();
    await assertAccessible(page);
    await capture(page, `login-${width}`);
    await page.getByRole("button", { name: "第一次使用" }).click();
    await expect(
      page.getByRole("button", { name: "下一步：選擇 Google 帳號" }),
    ).toBeDisabled();
    await page.getByLabel("怎麼稱呼你？").fill("林小森");
    await expect(
      page.getByRole("button", { name: "下一步：選擇 Google 帳號" }),
    ).toBeEnabled();
    await assertAccessible(page);
    await page.getByText("使用原帳號密碼登入", { exact: true }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByLabel("密碼", { exact: true })).toBeVisible();
  });
  test(`等待審核與舊帳號設定 ${width}px 不混用`, async ({ page }) => {
    let password = false;
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() =>
      sessionStorage.setItem("access_token", "synthetic-access"),
    );
    await page.route("**/v1/auth/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/account"))
        return route.fulfill({ json: profile(password) });
      if (path.includes("/join-target/"))
        return route.fulfill({ json: { id: org, name: "毛孩幸福之家" } });
      if (path.endsWith("/join-applications"))
        return route.fulfill({
          json: [
            {
              id: "request",
              organization_id: org,
              organization_name: "毛孩幸福之家",
              user_id: user,
              status: "pending",
              role: null,
              display_name: "林小森",
              created_at: "2026-09-07T00:00:00Z",
              reviewed_at: null,
            },
          ],
        });
      return route.fulfill({ json: { enabled: false } });
    });
    await page.goto(`/access?join=${org}`);
    await expect(
      page.getByRole("button", { name: "已送出申請" }),
    ).toBeDisabled();
    await expect(page.getByRole("link", { name: "登入設定" })).toHaveCount(0);
    await assertAccessible(page);
    await capture(page, `pending-${width}`);
    await page.goto("/account");
    await expect(page).toHaveURL(/\/access$/);
    password = true;
    await page.goto("/account");
    await expect(page.getByRole("heading", { name: "登入設定" })).toBeVisible();
    await expect(page.getByText("原帳號：lin.sen")).toBeVisible();
    await assertAccessible(page);
    await capture(page, `settings-${width}`);
  });
}

test("已授權單一收容所直接進入，多收容所保留選擇", async ({ page }) => {
  let organizations = [
    { id: org, code: "A", name: "毛孩幸福之家", role: "STAFF" },
  ];
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "synthetic-access"),
  );
  await page.route("**/v1/auth/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/account"))
      return route.fulfill({ json: profile(false, organizations) });
    if (path.endsWith("/active-shelter-context")) {
      expect(route.request().postDataJSON()).toEqual({ organization_id: org });
      return route.fulfill({ json: { organization_id: org } });
    }
    return route.fulfill({ json: [] });
  });
  // Stop at the handoff destination; workbench behavior is covered separately.
  await page.route(/\/\?_rsc=/, (route) => route.abort());
  const request = page.waitForRequest((request) =>
    request.url().endsWith("/v1/auth/active-shelter-context"),
  );
  await page.goto("/access?entry=1");
  await request;
  await expect
    .poll(() =>
      page.evaluate(() => sessionStorage.getItem("active_organization_id")),
    )
    .toBe(org);
  organizations = [
    ...organizations,
    { id: user, code: "B", name: "新店動物之家", role: "SHELTER_ADMIN" },
  ];
  await page.goto("/access?entry=1");
  await expect(page.getByRole("button", { name: "進入工作台" })).toHaveCount(2);
  await assertAccessible(page);
  await capture(page, "shelters-desktop");
});

test("姓名選單只替舊帳密帳號顯示登入設定", async ({ page }) => {
  let password = false;
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "synthetic-access"),
  );
  await mockManagementApi(page, {
    platformRole: null,
    memberships: [
      {
        id: "membership-org-a",
        organization_id: "org-a",
        role: "SHELTER_ADMIN",
        status: "active",
      },
    ],
  });
  await page.route("**/v1/auth/account", (route) =>
    route.fulfill({ json: profile(password) }),
  );
  await page.goto("/");
  const menu = page.getByLabel(/的帳號選單/);
  await menu.click();
  await expect(
    page.getByRole("link", { name: "我的收容所", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "登入設定" })).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "加入申請", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("link", { name: "我的收容所", exact: true }),
  ).toBeHidden();
  password = true;
  await page.reload();
  await menu.click();
  await expect(page.getByRole("link", { name: "登入設定" })).toBeVisible();
});
