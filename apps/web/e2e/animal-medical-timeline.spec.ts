import { expect, test } from "@playwright/test";
import { mockManagementApi } from "./fixtures";

test("動物時間軸同日顯示已發生醫療事件與預定提醒", async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  await mockManagementApi(page, {
    timelines: () => ({
      animal_id: "animal-a",
      organization_timezone: "Asia/Taipei",
      days: [
        {
          date: "2026-08-16",
          has_report: false,
          report_count: 0,
          has_activity: true,
          event_count: 1,
          reports: [],
          events: [
            {
              id: "m1",
              kind: "medical_record",
              occurrence: "actual",
              title: "量體重",
              summary: "12 公斤",
            },
          ],
          scheduled: [
            {
              id: "r1",
              kind: "care_reminder",
              occurrence: "scheduled",
              title: "吃藥",
              status: "pending",
              scheduled_at: "2026-08-16T09:00:00+08:00",
            },
          ],
        },
      ],
    }),
  });
  await page.goto("/animals/animal-a/timeline");
  await expect(page.getByRole("heading", { name: "已發生事件" })).toBeVisible();
  await expect(page.getByLabel("預定 吃藥").getByText("預定照護")).toBeVisible();
  await expect(page.getByText("量體重")).toBeVisible();
  await expect(page.getByText("吃藥")).toBeVisible();
});

test("時間軸載入失敗顯示錯誤而不渲染醫療資料", async ({ page }) => {
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "test-access"),
  );
  await mockManagementApi(page, { timelineStatus: 500 });
  await page.goto("/animals/animal-a/timeline");
  await expect(page.getByText("歷程載入失敗")).toBeVisible();
  await expect(page.getByText("量體重")).not.toBeVisible();
});
