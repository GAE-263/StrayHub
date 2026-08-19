import { expect, test } from "@playwright/test";
import { mockManagementApi } from "./fixtures";

const baseRecord = {
  id: "record-1",
  animal_id: "animal-a",
  occurred_at: "2026-08-16T01:00:00Z",
  occurred_timezone: "Asia/Taipei",
  record_type: "visit",
  title: "回診",
  content: "完成皮膚檢查",
  clinic: "森之心動物醫院",
  veterinarian: "王醫師",
  weight_kg: 12.5,
  status: "active",
  version: 1,
  created_by_user_id: "user-a",
  created_at: "2026-08-16T01:00:00Z",
  updated_by_user_id: "user-a",
  updated_at: "2026-08-16T01:00:00Z",
  archived_at: null,
  archive_reason: null,
  media_ids: [],
};

test("管理員可新增同日醫療歷史、搜尋、更正與封存", async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  let records = [baseRecord];
  let archiveRequests = 0;
  await mockManagementApi(page, {
    timelines: () => ({ days: [] }),
  });
  await page.route(
    "**/v1/management/animals/animal-a/medical-records**",
    async (route) => {
      if (route.request().method() === "POST") {
        const payload = JSON.parse(route.request().postData() ?? "{}");
        const created = {
          ...baseRecord,
          id: "record-2",
          title: payload.title,
          content: payload.content,
          record_type: payload.record_type,
          weight_kg: payload.weight_kg,
        };
        records = [created, ...records];
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify(created),
        });
        return;
      }
      const url = new URL(route.request().url());
      const search = url.searchParams.get("search");
      const filtered = search
        ? records.filter((record) =>
            `${record.title} ${record.content}`.includes(search),
          )
        : records;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: filtered, next_cursor: null }),
      });
    },
  );
  await page.route(
    "**/v1/management/medical-records/record-1**",
    async (route) => {
      const payload = JSON.parse(route.request().postData() ?? "{}");
      const current = {
        ...baseRecord,
        ...payload,
        version: 2,
        status: "active",
      };
      if (route.request().method() === "PATCH") {
        records = records.map((record) =>
          record.id === "record-1" ? current : record,
        );
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(current),
        });
        return;
      }
      if (route.request().method() === "POST") {
        archiveRequests += 1;
        if (archiveRequests === 1) {
          await route.fulfill({ status: 503, body: "offline" });
          return;
        }
        const archived = {
          ...current,
          status: "archived",
          archived_at: "2026-08-16T02:00:00Z",
          archive_reason: payload.reason,
          version: 3,
        };
        records = records.map((record) =>
          record.id === "record-1" ? archived : record,
        );
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(archived),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(current),
      });
    },
  );

  await page.goto("/animals/animal-a/timeline");
  await expect(page.getByRole("heading", { name: "醫療歷史" })).toBeVisible();
  await expect(page.getByText("完成皮膚檢查")).toBeVisible();

  await page
    .getByRole("textbox", { name: "標題", exact: true })
    .fill("同日第二筆");
  await page
    .getByRole("textbox", { name: "內容", exact: true })
    .fill("記錄疫苗與體重");
  await page.getByLabel("類型", { exact: true }).selectOption("vaccination");
  await page.getByLabel("體重（公斤，選填）").fill("13.1");
  await page
    .locator("form")
    .evaluate((form) => (form as HTMLFormElement).requestSubmit());
  await expect(page.getByText("已儲存醫療紀錄")).toBeVisible();
  await expect(page.getByText("同日第二筆")).toBeVisible();

  await page.getByLabel("搜尋標題或內容").fill("皮膚");
  await expect(page.getByText("完成皮膚檢查")).toBeVisible();
  await expect(page.getByText("同日第二筆")).not.toBeVisible();

  await page.getByLabel("搜尋標題或內容").fill("");
  const visitRecord = page.getByRole("article").filter({ hasText: "回診" });
  await visitRecord.getByRole("button", { name: "修改／封存" }).click();
  await page.getByLabel("內容").last().fill("完成皮膚與耳朵檢查");
  await page.getByLabel("修改或封存原因").fill("補充醫師說明");
  await page.getByRole("button", { name: "儲存修改" }).click();
  await expect(page.getByText("已更新醫療紀錄")).toBeVisible();
  await expect(page.getByText("完成皮膚與耳朵檢查")).toBeVisible();

  await visitRecord.getByRole("button", { name: "修改／封存" }).click();
  await page.getByLabel("修改或封存原因").fill("重複紀錄");
  await page.getByRole("button", { name: "封存紀錄" }).click();
  await expect(
    page.getByRole("heading", { name: "確認封存醫療紀錄" }),
  ).toBeVisible();
  expect(archiveRequests).toBe(0);
  await page.getByRole("button", { name: "取消封存" }).click();
  expect(archiveRequests).toBe(0);
  await page.getByRole("button", { name: "封存紀錄" }).click();
  const archiveDialog = page.getByRole("alertdialog");
  await archiveDialog.getByRole("button", { name: "確認封存" }).click();
  await expect(archiveDialog).toBeVisible();
  await expect(archiveDialog.getByRole("alert")).toContainText(
    "醫療紀錄封存失敗",
  );
  await expect(archiveDialog).toContainText("重複紀錄");
  expect(archiveRequests).toBe(1);
  await archiveDialog.getByRole("button", { name: "取消封存" }).click();
  await expect(archiveDialog).not.toBeVisible();
  await expect(
    page.getByRole("alert").filter({ hasText: "醫療紀錄封存失敗" }),
  ).toHaveCount(0);
  await expect(page.getByLabel("修改或封存原因")).toHaveValue("重複紀錄");
  await page.getByRole("button", { name: "封存紀錄" }).click();
  await archiveDialog.getByRole("button", { name: "確認封存" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "已封存醫療紀錄" }),
  ).toBeVisible();
  expect(archiveRequests).toBe(2);
});

test("附件或網路失敗時保留尚未送出的醫療文字", async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  await mockManagementApi(page, { timelines: () => ({ days: [] }) });
  await page.route(
    "**/v1/management/animals/animal-a/medical-records**",
    async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 422,
          contentType: "application/json",
          body: JSON.stringify({
            code: "medical_media_invalid",
            message: "附件失敗",
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], next_cursor: null }),
      });
    },
  );
  await page.goto("/animals/animal-a/timeline");
  await page
    .getByRole("textbox", { name: "標題", exact: true })
    .fill("附件失敗仍保留");
  await page
    .getByRole("textbox", { name: "內容", exact: true })
    .fill("這段文字不可遺失");
  await page
    .locator("form")
    .evaluate((form) => (form as HTMLFormElement).requestSubmit());
  await expect(
    page.getByRole("alert").filter({ hasText: "醫療紀錄儲存失敗" }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "標題", exact: true }),
  ).toHaveValue("附件失敗仍保留");
  await expect(
    page.getByRole("textbox", { name: "內容", exact: true }),
  ).toHaveValue("這段文字不可遺失");
});

test("未授權的動物 deep-link 不會渲染醫療內容", async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "staff-token");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  await mockManagementApi(page, { timelines: () => ({ days: [] }) });
  await page.route(
    "**/v1/management/animals/other-animal/medical-records**",
    async (route) => {
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: JSON.stringify({
          code: "medical_care_access_denied",
          message: "無權查看醫療資料",
        }),
      });
    },
  );
  await page.goto("/animals/other-animal/timeline");
  await expect(
    page.getByRole("alert").filter({ hasText: "醫療歷史載入失敗" }),
  ).toBeVisible();
  await expect(page.getByText("完成皮膚檢查")).not.toBeVisible();
});
