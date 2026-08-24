import { expect, test } from "@playwright/test";

function localDate(value: Date): string {
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${value.getFullYear()}-${month}-${day}`;
}

test("review page opens the nearest pending service date and preserves it in explicit decisions", async ({
  page,
}) => {
  const today = localDate(new Date());
  const nextDateValue = new Date();
  nextDateValue.setDate(nextDateValue.getDate() + 1);
  const nextDate = localDate(nextDateValue);
  let submittedSelection: unknown = null;

  await page.addInitScript(() => {
    window.sessionStorage.setItem("access_token", "local-token");
    window.sessionStorage.setItem("active_organization_id", "org-a");
    window.sessionStorage.setItem("active_organization_code", "ORG-A");
  });
  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url());
    let body: unknown = {};
    let status = 200;
    if (url.pathname.endsWith("/auth/me")) {
      body = {
        user: { id: "admin-a", display_name: "管理員", status: "active" },
        memberships: [
          {
            id: "membership-a",
            organization_id: "org-a",
            role: "SHELTER_ADMIN",
            status: "active",
          },
        ],
      };
    } else if (url.pathname.endsWith("/auth/active-shelter-context")) {
      body = { organization_id: "org-a" };
    } else if (url.pathname === "/v1/organizations") {
      body = { items: [{ id: "org-a", code: "ORG-A", name: "收容所 A" }] };
    } else if (url.pathname.endsWith("/volunteer-applications")) {
      const serviceDate = url.searchParams.get("service_date");
      body = {
        items:
          serviceDate === nextDate
            ? [
                {
                  id: "application-a",
                  display_name: "LINE 志工",
                  status: "pending",
                  version: 1,
                },
              ]
            : [],
        matching_count: serviceDate === nextDate ? 1 : 0,
        next_cursor: null,
        available_service_dates: [
          { service_date: nextDate, pending_count: 1 },
        ],
      };
    } else if (url.pathname.endsWith("/volunteer-decision-batches")) {
      submittedSelection = JSON.parse(
        route.request().postData() ?? "{}",
      ).selection;
      status = 201;
      body = {
        id: "batch-a",
        requested_count: 1,
        processed_count: 0,
        succeeded_count: 0,
        conflict_count: 0,
        failed_count: 0,
        status: "queued",
      };
    } else if (url.pathname.endsWith("/items")) {
      body = { items: [], next_cursor: null };
    }
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });

  await page.goto("/volunteers/applications");

  await expect(page.locator('input[type="date"]')).toHaveValue(nextDate);
  await expect(page.getByText("LINE 志工")).toBeVisible();
  await expect(
    page.getByText(`目前顯示 ${nextDate} 的待審核申請`, { exact: true }),
  ).toBeVisible();
  expect(today).not.toBe(nextDate);

  await page.getByRole("checkbox", { name: "選取 LINE 志工" }).check();
  await page.getByRole("button", { name: "確認並建立批次" }).click();
  await page.getByRole("button", { name: "送出完整快照" }).click();
  await expect(page.getByText("批次已建立")).toBeVisible();
  expect(submittedSelection).toEqual({
    mode: "explicit_items",
    service_date: nextDate,
    items: [
      {
        application_id: "application-a",
        expected_version: 1,
        expires_at: null,
      },
    ],
  });
});
