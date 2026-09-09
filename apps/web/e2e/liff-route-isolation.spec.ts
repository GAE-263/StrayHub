import { test, expect } from "@playwright/test";
import { mockManagementApi } from "./fixtures";

test.describe("LIFF 志工入口 route isolation", () => {
  test("shared LIFF onboarding route scrubs a legacy LINE token", async ({
    page,
  }) => {
    await page.goto(
      "/volunteer-application?entry=local-entry&id_token=legacy-token",
      { waitUntil: "commit" },
    );

    await expect(page).toHaveURL(/\/volunteer-application\?entry=local-entry$/);
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

  test("invalid organization target fails safely before LINE or protected API access", async ({
    page,
  }) => {
    const protectedRequests: string[] = [];
    page.on("request", (request) => {
      const pathname = new URL(request.url()).pathname;
      if (
        pathname.startsWith("/v1/auth/") ||
        pathname.startsWith("/v1/organizations") ||
        pathname.startsWith("/v1/management/")
      ) {
        protectedRequests.push(pathname);
      }
    });
    await page.route("**/v1/public/volunteer-organizations", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ regions: [] }),
      }),
    );

    await page.goto(
      "/volunteer-application?organization_id=client-controlled-invalid",
    );

    await expect(
      page.getByRole("heading", { name: "此收容所目前無法報名" }),
    ).toBeVisible();
    await expect(
      page.getByText("連結已失效，或該收容所目前未開放志工申請。"),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "重新選擇地區與收容所" }),
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
    const organizationSelect = page.getByLabel("切換目前收容所");
    await expect(organizationSelect).toHaveValue("org-a");

    await organizationSelect.selectOption("org-b");

    await expect(organizationSelect).toHaveValue("org-b");
    await expect(organizationSelect.locator("option:checked")).toHaveText(
      /ORG-B/,
    );
  });
});
