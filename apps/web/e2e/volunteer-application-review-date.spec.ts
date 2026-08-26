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
    } else if (
      url.pathname.endsWith("/volunteer-applications/application-a/pii-reveal")
    ) {
      body = {
        applicant_name: "核准顯示名",
        phone_number: "0900000000",
        basic_profile: { experience: "synthetic" },
      };
    } else if (
      url.pathname.endsWith(
        "/volunteer-applications/application-a/service-summary",
      )
    ) {
      expect(url.searchParams.get("purpose_code")).toBe(
        "volunteer_service_history_review",
      );
      body = {
        items: [
          {
            organization_id: "org-b",
            organization_name: "收容所 B",
            service_date: "2026-05-20",
            service_status: "recorded",
            record_count: 2,
            source: "care_report",
          },
        ],
        next_cursor: null,
      };
    } else if (url.pathname.endsWith("/volunteer-applications/application-a")) {
      body = {
        id: "application-a",
        organization_id: "org-a",
        display_name: "LINE 志工",
        status: "pending",
        submitted_at: "2026-08-24T00:00:00Z",
        decided_at: null,
        decision_reason: null,
        version: 1,
        service_dates: [
          {
            service_date: nextDate,
            status: "pending",
            decided_at: null,
            decision_reason: null,
            version: 1,
          },
        ],
      };
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
        available_service_dates: [{ service_date: nextDate, pending_count: 1 }],
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

  await page.getByRole("button", { name: "查看申請資料" }).click();
  await expect(page.getByRole("dialog")).toContainText("LINE 志工");
  await expect(page.getByRole("dialog")).toContainText("核准顯示名");
  await expect(page.getByRole("dialog")).toContainText("0900000000");
  await expect(
    page.getByRole("button", { name: "申請審核用途揭露" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "載入服務紀錄" }).click();
  await expect(page.getByRole("dialog")).toContainText("收容所 B");
  await page.getByRole("button", { name: "關閉申請人資料" }).click();
  await expect(page.getByText("核准顯示名", { exact: true })).toHaveCount(0);
  await expect(page.getByText("0900000000", { exact: true })).toHaveCount(0);
  await expect(page.getByText("收容所 B", { exact: true })).toHaveCount(0);

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
