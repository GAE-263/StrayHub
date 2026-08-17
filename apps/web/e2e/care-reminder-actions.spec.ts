import { expect, test } from "@playwright/test";

const pending = {
  occurrence_id: "occ-1",
  version: 0,
  status: "pending",
  animal: {
    id: "animal-1",
    name: "小白",
    shelter_number: "A-001",
    photo_url: null,
  },
  reminder_type: "medication",
  title: "每月預防藥",
  instructions: "依管理員輸入指示執行",
  display_local_at: "2026-08-16T09:00:00+08:00",
  can_complete: true,
  can_skip: true,
};

test("被指派志工可在三步內完成或略過提醒", async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  let action: string | null = null;
  await page.route("**/v1/assigned-care-reminders/occ-1**", async (route) => {
    if (route.request().method() === "POST") {
      action = JSON.parse(route.request().postData() ?? "{}").action;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          occurrence: {
            ...pending,
            version: 1,
            status: action === "complete" ? "completed" : "skipped",
            can_complete: false,
            can_skip: false,
          },
          action_id: "action-1",
          action_type: action === "complete" ? "completed" : "skipped",
          acted_at: "2026-08-16T01:00:00Z",
          recorded_at: action === "complete" ? "2026-08-16T01:00:00Z" : null,
          actual_completed_at:
            action === "complete" ? "2026-08-16T01:00:00Z" : null,
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(pending),
    });
  });
  await page.goto("/assigned-care/occ-1");
  await expect(
    page.getByRole("heading", { name: "我的照護指派" }),
  ).toBeVisible();
  // Submit the form directly so a transient Next dev overlay cannot intercept
  // the interaction while this newly added route recompiles.
  await page
    .locator("form")
    .evaluate((form) => (form as HTMLFormElement).requestSubmit());
  await expect.poll(() => action).toBe("complete");
});
