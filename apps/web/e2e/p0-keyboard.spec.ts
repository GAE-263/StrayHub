import { test, expect } from "@playwright/test";
import { mockManagementApi } from "./fixtures";
import {
  mockLiffBrowser,
  mockVolunteerAccessApi,
} from "./volunteer-access-fixtures";

async function mockVolunteerEntryNew(
  page: Parameters<typeof mockLiffBrowser>[0],
) {
  await mockLiffBrowser(page);
  await page.route("**/v1/auth/liff/exchange", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        state: "NEW",
        organization: {
          id: "org-a",
          code: "ORG-A",
          name: "收容所 A",
        },
        user: { role: "VOLUNTEER" },
      }),
    });
  });
  await page.route("**/v1/volunteer-applications/status", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        organization: {
          id: "org-a",
          name: "收容所 A",
          applications_enabled: true,
          insurance_required: false,
        },
        application: null,
        grant: null,
        effective_status: "none",
        next_actions: ["apply"],
      }),
    });
  });
}

test("登入核心操作可用鍵盤完成", async ({ page }) => {
  await page.goto("/login");
  const passwordLogin = page.getByText("使用原帳號密碼登入", {
    exact: true,
  });
  await passwordLogin.focus();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("帳號")).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("密碼")).toBeFocused();
});

test("志工入口 NEW 狀態可用鍵盤進入報名", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await mockVolunteerEntryNew(page);
  await page.goto(
    "/volunteer-entry?entry=opaque-entry-reference-0123456789abcdef-extra",
  );
  await expect(
    page.getByRole("heading", { name: "尚未完成志工報名" }),
  ).toBeVisible();

  const enterApplication = page.getByRole("button", {
    name: "進入志工報名",
  });
  await enterApplication.focus();
  await expect(enterApplication).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "收容所 A" })).toBeVisible();

  const consent = page.getByRole("checkbox", {
    name: "我確認送出志工報名，並同意由此收容所審核。",
  });
  await consent.focus();
  await page.keyboard.press("Space");
  await expect(consent).toBeChecked();
});

test("管理手機導覽可用鍵盤開關並恢復 focus", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "test-access"),
  );
  await mockManagementApi(page);
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "開啟管理工作台導覽" });
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("dialog", { name: "管理工作台導覽" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
});

test("志工搜尋與照護表單可用鍵盤操作", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "test-access"),
  );
  await mockManagementApi(page);
  await page.goto("/animal-confirmation");
  const fallback = page.getByRole("button", { name: "輸入完整收容編號" });
  await fallback.focus();
  await page.keyboard.press("Enter");
  const query = page.getByRole("textbox", { name: "完整收容編號" });
  await query.focus();
  await page.keyboard.type("A-001");
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "確認照護動物" }),
  ).toBeVisible();

  await page.goto("/care-report");
  await expect(
    page.getByRole("heading", { name: "照護回報備援介面" }),
  ).toBeVisible();
  const save = page.getByRole("button", { name: "儲存並繼續" });
  await save.focus();
  await expect(save).toBeEnabled();
});

test("管理核心搜尋、篩選、detail 與 Timeline 展開可用鍵盤完成", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  await mockManagementApi(page, {
    animals: () => ({
      items: [
        {
          id: "animal-a",
          name: "小森",
          shelter_number: "A-001",
          status: "active",
          area_name: "一區",
          area_type: "room",
        },
      ],
      page: 1,
      page_size: 20,
      total: 1,
    }),
    reports: () => ({
      items: [
        {
          id: "report-a",
          animal_id: "animal-a",
          animal_name: "小森",
          status: "saved",
          ai_job_status: "processing",
          submitted_at: "2026-08-14T00:00:00Z",
          note: null,
        },
      ],
      page: 1,
      page_size: 50,
      total: 1,
    }),
    timelines: () => ({
      days: [
        {
          date: "2026-08-14",
          has_report: true,
          report_count: 1,
          reports: [
            {
              id: "report-a",
              note: "鍵盤展開測試",
              ai_job_status: "processing",
              status: "saved",
            },
          ],
        },
      ],
    }),
  });

  await page.goto("/animals");
  const query = page.getByLabel("搜尋");
  await query.focus();
  await page.keyboard.type("小森");
  await expect(page.getByRole("link", { name: "小森" })).toBeVisible();
  await page.getByRole("link", { name: "小森" }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/animals\/animal-a$/);

  await page.goto("/reports");
  const status = page.getByLabel("處理狀態", { exact: true });
  await status.focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByText("小森")).toBeVisible();
  await page.getByRole("link", { name: /小森/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/reports\/report-a$/);

  await page.goto("/animals/animal-a/timeline");
  const reports = page.getByRole("button", { name: "有回報：1 筆" });
  await reports.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("鍵盤展開測試")).toBeVisible();
});

test("照護行事曆日期與篩選可由鍵盤操作", async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  await mockManagementApi(page);
  await page.goto("/care-calendar");
  await expect(page.getByRole("heading", { name: "照護行事曆" })).toBeVisible();
  const date = page.getByLabel("日期");
  await date.focus();
  await page.keyboard.press("ArrowDown");
  await expect(date).toBeFocused();
});

test("毛孩日記搜尋、篩選與 AI 來源可由鍵盤操作", async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  await mockManagementApi(page);
  await page.goto("/growth-diary");
  const query = page.getByLabel("動物名稱或收容編號");
  await query.focus();
  await page.keyboard.type("米糕");
  await page.keyboard.press("Tab");
  const mood = page.getByLabel("關注狀態");
  await expect(mood).toBeFocused();
  await mood.selectOption("concern");
  const search = page.getByRole("button", { name: "搜尋", exact: true });
  await search.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("org-a 米糕", { exact: true })).toBeVisible();

  const provenance = page
    .locator("article", { hasText: "org-a 米糕" })
    .getByRole("button", { name: /AI 來源/ });
  await provenance.focus();
  await page.keyboard.press("Enter");
  await expect(provenance).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText("AI 原始輸出")).toBeVisible();
});

test("Sheet 的 Escape、取消與 focus restore 可用鍵盤完成", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "test-access"),
  );
  await mockManagementApi(page);
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "開啟管理工作台導覽" });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const sheet = page.getByRole("dialog", { name: "管理工作台導覽" });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole("button", { name: "關閉" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  await expect(trigger).toBeFocused();

  await trigger.press("Enter");
  await sheet.getByRole("button", { name: "關閉" }).click();
  await expect(trigger).toBeFocused();
});

test("Report detail AlertDialog 可用 Escape／取消並 restore focus", async ({
  page,
}) => {
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "test-access"),
  );
  await mockManagementApi(page);
  await page.goto("/reports/report-a");
  await page.getByText("更正回報／封存").click();
  await page.getByLabel("更正或封存原因").fill("鍵盤確認封存流程");
  const archive = page.getByRole("button", { name: "封存回報", exact: true });
  await archive.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("alertdialog", { name: "確認封存回報" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "關閉" })).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(archive).toBeFocused();

  await archive.press("Enter");
  await dialog.getByRole("button", { name: "取消" }).click();
  await expect(archive).toBeFocused();
});

test("志工批次期限、確認 dialog、live result 與通知重試可由鍵盤操作", async ({
  page,
}) => {
  await mockVolunteerAccessApi(page);
  await page.goto("/volunteers/applications");
  const allFiltered = page.getByRole("checkbox", {
    name: /目前篩選結果全部/,
  });
  await allFiltered.focus();
  await page.keyboard.press("Space");
  await expect(allFiltered).toBeChecked();
  const individual = page.getByLabel(/王小明.*個別到期時間/);
  const selectedApplicant = page.getByLabel(/選取 王小明/);
  await selectedApplicant.focus();
  await page.keyboard.press("Space");
  await individual.focus();
  await individual.fill("2026-08-22T12:00");
  await expect(individual).toHaveValue("2026-08-22T12:00");
  const create = page.getByRole("button", { name: "確認並建立批次" });
  await create.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("alertdialog", {
    name: "確認志工批次決策",
  });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "關閉批次確認" }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(create).toBeFocused();
  await create.press("Enter");
  await dialog.getByRole("button", { name: "送出完整快照" }).press("Enter");
  await expect(page.getByRole("status").last()).toContainText("批次已建立");
  await expect(page.getByRole("status").last()).toHaveAttribute(
    "aria-live",
    "polite",
  );

  await page.goto("/volunteers/notifications");
  const filter = page.getByRole("button", { name: "套用篩選" });
  await filter.focus();
  await expect(filter).toBeFocused();
  const failed = page.getByRole("checkbox", { name: "選取 志工 A 通知" });
  await failed.focus();
  await page.keyboard.press("Space");
  const retry = page.getByRole("button", { name: "重試已選取（1）" });
  await retry.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").last()).toContainText(
    "已重新排入 1 筆",
  );
});
