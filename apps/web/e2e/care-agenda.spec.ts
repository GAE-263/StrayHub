import { expect, test } from "@playwright/test";
import { mockManagementApi } from "./fixtures";

test("今日照護行事曆顯示四區、欄位與篩選", async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  await mockManagementApi(page);
  await page.route("**/v1/management/care-agenda**", async (route) => {
    const cursor = new URL(route.request().url()).searchParams.get(
      "today_pending_cursor",
    );
    const item =
      cursor === "1"
        ? {
            occurrence_id: "o2",
            animal_id: "animal-b",
            animal_name: "阿福",
            shelter_number: "A-002",
            reminder_type: "follow_up",
            title: "回診",
            instructions: "依管理員指示執行",
            scheduled_at: "2026-08-16T10:00:00+08:00",
            status: "pending",
            version: 0,
            is_virtual: true,
            assignee_membership_id: null,
          }
        : {
            occurrence_id: "o1",
            animal_id: "animal-a",
            animal_name: "小白",
            shelter_number: "A-001",
            reminder_type: "medication",
            title: "吃藥",
            instructions: "依管理員指示執行",
            scheduled_at: "2026-08-16T09:00:00+08:00",
            status: "pending",
            version: 0,
            is_virtual: true,
            assignee_membership_id: null,
          };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        local_today: "2026-08-16",
        timezone: "Asia/Taipei",
        timezone_version: 1,
        buckets: {
          today_pending: [item],
          overdue: [],
          today_resolved: [],
          next_seven_days: [],
        },
        totals: {
          today_pending: 2,
          overdue: 0,
          today_resolved: 0,
          next_seven_days: 0,
        },
        pages: {
          today_pending: {
            items: [item],
            total_count: 2,
            next_cursor: cursor === "1" ? null : "1",
          },
          overdue: { items: [], total_count: 0, next_cursor: null },
          today_resolved: { items: [], total_count: 0, next_cursor: null },
          next_seven_days: { items: [], total_count: 0, next_cursor: null },
        },
      }),
    });
  });
  await page.goto("/care-calendar");
  await expect(page.getByRole("heading", { name: "照護行事曆" })).toBeVisible();
  await expect(page.getByText("今天待處理")).toBeVisible();
  await expect(page.getByText("已逾期")).toBeVisible();
  await expect(page.getByText("小白")).toBeVisible();
  await expect(page.getByLabel("今天待處理").getByText("吃藥")).toBeVisible();
  await expect(page.getByLabel("今天待處理")).toContainText("1 / 2");
  await page.getByRole("button", { name: "載入更多（尚有 1 筆）" }).click();
  await expect(page.getByLabel("今天待處理").getByText("阿福")).toBeVisible();
  await expect(page.getByLabel("今天待處理")).toContainText("2");
});
