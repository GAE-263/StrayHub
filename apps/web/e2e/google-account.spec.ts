import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const organization = "00000000-0000-4000-8000-000000000001";
const user = "00000000-0000-4000-8000-000000000002";

test("manager chooses role at approval and rejected requests leave the pending list", async ({
  page,
}) => {
  let items = ["first", "second"].map((id) => ({
    id,
    organization_id: organization,
    organization_name: "測試收容所",
    user_id: user,
    display_name: id === "first" ? "王小明" : "李小華",
    status: "pending",
    role: null,
    created_at: "2026-09-07T00:00:00Z",
    reviewed_at: null,
  }));
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "synthetic-access"),
  );
  await page.route("**/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/active-shelter-context"))
      return route.fulfill({ json: { organization_id: organization } });
    if (path.endsWith("/decision")) {
      const id = path.split("/").at(-2);
      expect(route.request().postDataJSON()).toEqual(
        id === "first"
          ? { approve: true, role: "SHELTER_ADMIN" }
          : { approve: false },
      );
      items = items.filter((item) => item.id !== id);
      return route.fulfill({
        json: { status: id === "first" ? "approved" : "rejected" },
      });
    }
    return route.fulfill({ json: items });
  });
  await page.goto(`/account/invitations?organization=${organization}`);
  await expect(
    page.getByRole("link", { name: /access\?join=/ }),
  ).toHaveAttribute("href", new RegExp(`join=${organization}$`));
  for (const width of [1440, 360]) {
    await page.setViewportSize({ width, height: 900 });
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
    await page.screenshot({
      path: `/tmp/strayhub-identity-review-${width}.png`,
      fullPage: true,
    });
  }
  const first = page.getByRole("article", { name: "王小明的申請" });
  await expect(first.getByRole("button", { name: "核准加入" })).toBeDisabled();
  await first.getByLabel("核准後權限").selectOption("SHELTER_ADMIN");
  await first.getByRole("button", { name: "核准加入" }).click();
  await expect(page.getByRole("heading", { name: /王小明/ })).toHaveCount(0);
  await page.getByRole("button", { name: "否決", exact: true }).click();
  await page.getByRole("button", { name: "確認否決" }).click();
  await expect(
    page.getByText("目前沒有待審申請", { exact: true }),
  ).toBeVisible();
});

test("fixed link survives the redirect to login without accepting external redirects", async ({
  page,
}) => {
  await page.route("**/v1/auth/google/config", (route) =>
    route.fulfill({ json: { enabled: false } }),
  );
  await page.goto(`/account?join=${organization}`);
  await expect(page).toHaveURL(new RegExp(`/login\\?join=${organization}$`));
});

test("Google-only account applies through fixed link and keeps its restricted session", async ({
  page,
}) => {
  let claimed = false;
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "synthetic-access");
    sessionStorage.setItem("refresh_token", "synthetic-refresh");
    sessionStorage.setItem("session_id", "synthetic-session");
  });
  await page.route("**/v1/auth/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/v1/auth/account")
      return route.fulfill({
        json: {
          user: {
            id: user,
            display_name: "新使用者",
            username: null,
            platform_role: null,
          },
          state: "account_only",
          organizations: [],
          login_methods: { google: true, password: false },
        },
      });
    if (path.startsWith("/v1/auth/join-target/"))
      return route.fulfill({ json: { id: organization, name: "測試收容所" } });
    if (
      path === "/v1/auth/join-applications" &&
      route.request().method() === "POST"
    ) {
      expect(route.request().method()).toBe("POST");
      expect(route.request().postDataJSON()).toEqual({
        organization_id: organization,
      });
      expect(route.request().headers()["x-strayhub-account"]).toBe("1");
      claimed = true;
      return route.fulfill({ json: { status: "pending" } });
    }
    if (path === "/v1/auth/join-applications")
      return route.fulfill({
        json: claimed
          ? [
              {
                id: "application",
                organization_id: organization,
                organization_name: "測試收容所",
                role: null,
                status: "pending",
                user_id: user,
                display_name: null,
                created_at: "2026-09-07T00:00:00Z",
                reviewed_at: null,
              },
            ]
          : [],
      });
    if (path === "/v1/auth/logout") return route.fulfill({ status: 204 });
    return route.fulfill({ json: { enabled: false } });
  });
  await page.goto(`/account?join=${organization}`);
  await expect(page.getByRole("heading", { name: "我的收容所" })).toBeVisible();
  await expect(page.getByRole("link", { name: "登入設定" })).toHaveCount(0);
  await expect(page.getByLabel("重新驗證原帳號密碼")).toHaveCount(0);
  expect(
    await page.evaluate(() => sessionStorage.getItem("access_token")),
  ).toBe("synthetic-access");
  await page.getByRole("button", { name: "送出加入申請" }).click();
  await expect(page.getByText("等待審核", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "已送出申請" })).toBeDisabled();
  await page.reload();
  await expect(page.getByText("等待審核", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 360, height: 800 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "登出", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(
    await page.evaluate(() => sessionStorage.getItem("access_token")),
  ).toBeNull();
});
