import { expect, test } from "@playwright/test";

import { mockManagementApi } from "./fixtures";

const organizationId = "567688df-15dc-45a7-aa1d-918f51eec62b";
const supportReason = "查詢志工申請與授權設定";
const encodedSupportReason = encodeURIComponent(supportReason);

test("platform admin supplies an audited reason before loading and saving volunteer policy", async ({
  page,
}) => {
  await mockManagementApi(page, {
    organizations: [
      {
        id: organizationId,
        code: "ORG-A",
        name: "浪浪森友會",
        role: "PLATFORM_ADMIN",
        status: "active",
        timezone: "Asia/Taipei",
        timezone_version: 1,
      },
    ],
  });
  await page.route("**/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user: {
          id: "platform-admin-a",
          username: "local-platform-admin",
          display_name: "本機平台管理員",
          platform_role: "PLATFORM_ADMIN",
          status: "active",
        },
        memberships: [],
      }),
    });
  });

  const policyRequests: Array<{ method: string; reason: string | undefined }> = [];
  await page.route("**/v1/organizations/*/volunteer-access-policy", async (route) => {
    const request = route.request();
    policyRequests.push({
      method: request.method(),
      reason: request.headers()["x-platform-support-reason"],
    });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        organization_id: organizationId,
        applications_enabled: request.method() === "GET",
        default_grant_duration_hours: 168,
        version: request.method() === "GET" ? 1 : 2,
      }),
    });
  });

  await page.addInitScript((activeOrganizationId) => {
    window.sessionStorage.setItem("access_token", "platform-admin-token");
    window.sessionStorage.setItem(
      "active_organization_id",
      activeOrganizationId,
    );
  }, organizationId);

  await page.goto("/settings/volunteer-access");
  await expect(page.getByLabel("平台支援原因")).toBeVisible();
  expect(policyRequests).toEqual([]);

  await page.getByLabel("平台支援原因").fill(supportReason);
  await page.getByRole("button", { name: "載入設定" }).click();
  await expect(page.getByRole("checkbox", { name: "開放志工新申請" })).toBeChecked();
  expect(policyRequests).toEqual([
    {
      method: "GET",
      reason: encodedSupportReason,
    },
  ]);

  await page.getByRole("checkbox", { name: "開放志工新申請" }).uncheck();
  await page.getByRole("button", { name: "儲存設定" }).click();
  await expect(page.getByText("設定已儲存，只影響後續建立的授權。")).toBeVisible();
  expect(policyRequests).toEqual([
    {
      method: "GET",
      reason: encodedSupportReason,
    },
    {
      method: "PATCH",
      reason: encodedSupportReason,
    },
  ]);
});
