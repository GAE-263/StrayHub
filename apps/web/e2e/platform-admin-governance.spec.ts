import { expect, test } from "@playwright/test";

test.describe("platform administrator governance", () => {
  test("platform admin can see global policy page without shelter selection", async ({
    page,
  }) => {
    await page.addInitScript(() =>
      sessionStorage.setItem("access_token", "platform-admin-test-token"),
    );
    await page.route("**/v1/**", async (route) => {
      const url = new URL(route.request().url());
      const json = async (body: unknown) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(body),
        });
      if (url.pathname.endsWith("/auth/me")) {
        await json({
          user: {
            id: "platform-admin",
            username: "local-platform-admin",
            display_name: "本機平台管理員",
            platform_role: "PLATFORM_ADMIN",
            status: "active",
          },
          memberships: [],
        });
        return;
      }
      if (url.pathname.endsWith("/auth/active-shelter-context")) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: "no shelter context" }),
        });
        return;
      }
      if (url.pathname === "/v1/organizations") {
        await json({ items: [] });
        return;
      }
      if (url.pathname.endsWith("/platform/administrators/candidates")) {
        await json([
          {
            user_id: "candidate-a",
            username: "local-staff-a",
            display_name: "本機工作人員 A",
          },
        ]);
        return;
      }
      if (url.pathname.endsWith("/platform/administrators/audit")) {
        await json([]);
        return;
      }
      if (url.pathname === "/v1/platform/administrators") {
        await json({
          policy: {
            min_active_admins: 1,
            max_active_admins: 2,
            active_count: 1,
            available_slots: 1,
          },
          items: [
            {
              user_id: "platform-admin",
              username: "local-platform-admin",
              display_name: "本機平台管理員",
              user_status: "active",
              platform_role: "PLATFORM_ADMIN",
              effective_status: "active",
              can_enable: false,
              can_disable: false,
              can_demote: false,
            },
          ],
        });
        return;
      }
      await json({});
    });
    await page.goto("/platform-admins");
    await expect(
      page.getByRole("heading", { name: "平台管理員", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("剩餘名額")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "啟用中的平台管理員", exact: true }),
    ).toBeVisible();
  });
});
