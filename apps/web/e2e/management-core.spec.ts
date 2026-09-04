import { test, expect } from "@playwright/test";
import { mockManagementApi } from "./fixtures";

test("管理核心 routes preserve empty state and navigation", async ({
  page,
}) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  await mockManagementApi(page);
  await page.goto("/animals");
  await expect(page.getByText("找不到符合條件的動物")).toBeVisible();

  for (const route of [
    "/reports",
    "/animals/animal-a",
    "/animals/animal-a/timeline",
    "/reports/report-a",
  ]) {
    await page.goto(route);
    await expect(page.locator("main").first()).toBeVisible();
  }
});

test("動物清單可用搜尋與 Cage／Area／狀態篩選找到資料", async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  await mockManagementApi(page, {
    areas: [{ id: "area-1", name: "一區", area_type: "room" }],
    animals: (params) => {
      const matches =
        params.get("query") === "小森" &&
        params.get("area_id") === "area-1" &&
        params.get("status") === "active";
      return {
        items: matches
          ? [
              {
                id: "animal-a",
                name: "小森",
                shelter_number: "A-001",
                status: "active",
                area_name: "一區",
                area_type: "room",
              },
            ]
          : [],
        page: 1,
        page_size: 20,
        total: matches ? 1 : 0,
      };
    },
  });
  await page.goto("/animals");
  await page.getByLabel("搜尋").fill("小森");
  await page.getByLabel("Cage／Area").selectOption("area-1");
  await expect(page.getByRole("link", { name: "小森" })).toBeVisible();
  await expect(page.getByText("A-001")).toBeVisible();
  await expect(page.getByRole("cell", { name: "一區" })).toBeVisible();
});

test("Report Inbox 可用日期與狀態篩選，並通往 detail 與 animal profile", async ({
  page,
}) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  await mockManagementApi(page, {
    reports: (params) => {
      const matches =
        params.get("from_date") === "2026-08-01" &&
        params.get("to_date") === "2026-08-14" &&
        params.get("status") === "saved";
      return {
        items: matches
          ? [
              {
                id: "report-a",
                animal_id: "animal-a",
                animal_name: "小森",
                status: "saved",
                ai_job_status: "processing",
                submitted_at: "2026-08-14T00:00:00Z",
                note: "原始回報",
              },
            ]
          : [],
        page: 1,
        page_size: 50,
        total: matches ? 1 : 0,
      };
    },
  });
  await page.goto("/reports");
  await page.getByLabel("開始日期").fill("2026-08-01");
  await page.getByLabel("結束日期").fill("2026-08-14");
  await page.getByLabel("狀態").selectOption("saved");
  await expect(page.getByText("小森")).toBeVisible();
  await expect(page.getByRole("link", { name: "查看詳情 →" })).toBeVisible();
  await page.getByRole("link", { name: "小森" }).click();
  await expect(page).toHaveURL(/\/animals\/animal-a$/);
  await expect(page.getByRole("heading", { name: "小森" })).toBeVisible();
  await page.getByRole("link", { name: "查看近期歷程" }).click();
  await expect(page).toHaveURL(/\/animals\/animal-a\/timeline$/);
});

test("detail 與 Timeline 保留 Breadcrumb、同日多筆與 AI／人工狀態", async ({
  page,
}) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  await mockManagementApi(page, {
    reportDetails: {
      "report-a": {
        id: "report-a",
        animal_id: "animal-a",
        animal_name: "小森",
        status: "saved",
        submitted_at: "2026-08-14T00:00:00Z",
        answers: { feeding: "normal" },
        note: "原始回報",
        media_ids: [],
        ai_observations: [
          {
            id: "observation-a",
            status: "succeeded",
            source_type: "note",
            raw_ai_output: { text: "ok" },
            validated_ai_observation: { code: "emotion.calm" },
            human_review_result: null,
          },
        ],
      },
    },
    timelines: () => ({
      days: [
        {
          date: "2026-08-14",
          has_report: true,
          report_count: 2,
          reports: [
            {
              id: "report-a",
              submitted_at: "2026-08-14T09:00:00+08:00",
              note: "同日第一筆",
              ai_job_status: "processing",
              status: "saved",
            },
            {
              id: "report-b",
              submitted_at: "2026-08-14T10:00:00+08:00",
              note: "同日第二筆",
              ai_job_status: "failed",
              status: "amended",
            },
          ],
        },
        { date: "2026-08-13", has_report: false, report_count: 0 },
      ],
    }),
  });

  await page.goto("/reports/report-a");
  await expect(page.getByRole("heading", { name: "小森" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("需要人工覆核");
  await expect(
    page.getByLabel("Breadcrumb").getByRole("link", { name: "回報收件匣" }),
  ).toBeVisible();

  await page.goto("/animals/animal-a/timeline");
  await expect(
    page.getByLabel("Breadcrumb").getByRole("link", { name: "動物檔案" }),
  ).toBeVisible();
  await expect(page.getByText("2026-08-14")).toBeVisible();
  await page.getByRole("button", { name: "有回報：2 筆" }).click();
  await expect(page.getByText("同日第一筆")).toBeVisible();
  await expect(page.getByText("同日第二筆")).toBeVisible();
  await expect(page.getByText("AI 處理中（processing）")).toBeVisible();
  await expect(page.getByText("AI 處理失敗（failed）")).toBeVisible();
  await expect(page.getByText("當日沒有事件")).toBeVisible();
});

test("較慢的舊查詢不得覆蓋最新回報篩選結果", async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  await mockManagementApi(page, {
    reports: (params) => {
      const status = params.get("status");
      const report =
        status === "saved"
          ? {
              id: "old-report",
              animal_id: "animal-a",
              animal_name: "舊條件結果",
              status: "saved",
              ai_job_status: "processing",
              submitted_at: "2026-08-14T00:00:00Z",
              note: null,
            }
          : {
              id: "new-report",
              animal_id: "animal-a",
              animal_name: "最新條件結果",
              status: "amended",
              ai_job_status: "succeeded",
              submitted_at: "2026-08-14T00:00:00Z",
              note: null,
            };
      return { items: [report], page: 1, page_size: 50, total: 1 };
    },
    reportDelay: (params) => (params.get("status") === "saved" ? 250 : 0),
  });
  await page.goto("/reports");
  await page.getByLabel("狀態").selectOption("saved");
  await page.getByLabel("狀態").selectOption("amended");
  await expect(page.getByText("最新條件結果")).toBeVisible();
  await page.waitForTimeout(350);
  await expect(page.getByText("最新條件結果")).toBeVisible();
  await expect(page.getByText("舊條件結果")).toHaveCount(0);
});
