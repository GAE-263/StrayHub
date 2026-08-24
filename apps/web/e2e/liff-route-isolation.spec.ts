import { test, expect } from "@playwright/test";
import { mockManagementApi } from "./fixtures";

test.describe("LIFF 志工入口 route isolation", () => {
  test("legacy onboarding URL redirects without retaining the LINE token", async ({
    page,
  }) => {
    await page.goto(
      "/volunteer-application?entry=local-entry&id_token=legacy-token",
      { waitUntil: "commit" },
    );

    await expect(page).toHaveURL(/\/volunteer-entry\?entry=local-entry$/);
    expect(new URL(page.url()).searchParams.has("id_token")).toBe(false);
  });

  test("public LIFF entry does not issue protected management requests", async ({
    page,
  }) => {
    const protectedRequests: string[] = [];
    page.on("request", (request) => {
      const pathname = new URL(request.url()).pathname;
      if (
        pathname.startsWith("/v1/auth/me") ||
        pathname.startsWith("/v1/organizations") ||
        pathname.startsWith("/v1/management/")
      ) {
        protectedRequests.push(pathname);
      }
    });
    await page.route("https://api.line.me/**", (route) => route.abort());

    await page.goto(
      "/volunteer-entry?entry=opaque-entry-reference-0123456789abcdef-extra",
      { waitUntil: "domcontentloaded" },
    );
    await expect(
      page.getByRole("heading", { name: "無法開啟志工服務" }),
    ).toBeVisible();
    expect(protectedRequests).toEqual([]);
  });

  test("A/B organization membership and active context remain explicit", async ({
    page,
  }) => {
    await page.addInitScript(() =>
      sessionStorage.setItem("access_token", "test-access"),
    );
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
      activeOrganizationId: "org-a",
      memberships: [
        {
          id: "membership-a",
          organization_id: "org-a",
          role: "STAFF",
          status: "active",
        },
        {
          id: "membership-b",
          organization_id: "org-b",
          role: "STAFF",
          status: "active",
        },
      ],
    });

    await page.goto("/");
    await expect(page.getByRole("combobox")).toHaveValue("org-a");

    await page.locator("select").selectOption("org-b");

    await expect(page.getByRole("combobox")).toHaveValue("org-b");
    await expect(page.locator("select option:checked")).toHaveText(/ORG-B/);
  });
});
