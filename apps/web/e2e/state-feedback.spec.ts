import { test, expect } from "@playwright/test";
import { mockLoginApi, mockManagementApi, mockVolunteerApi } from "./fixtures";

test("dashboard loading and empty states provide a next step", async ({
  page,
}) => {
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "test-access"),
  );
  await mockManagementApi(page);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "管理工作台總覽" }),
  ).toBeVisible();
  await expect(page.getByText("目前沒有最近回報")).toBeVisible();
});

test("saving failure preserves volunteer input and retry can succeed", async ({
  page,
}) => {
  const mock = await mockVolunteerApi(page, { saveStatus: 500 });
  await page.goto("/care-report");
  const note = page.getByLabel("補充心得（選填）");
  await note.fill("現場原始觀察，不應在保存失敗時消失。");
  const save = page.locator('button[aria-describedby="save-status"]');
  await save.click();
  await expect(
    page.getByText("草稿保存失敗，已保留原始輸入，請重試。"),
  ).toBeVisible();
  await expect(note).toHaveValue("現場原始觀察，不應在保存失敗時消失。");

  mock.setSaveStatus(200);
  await save.click();
  await expect(
    page.getByText("草稿已保存，可回到 LINE Bot 繼續。"),
  ).toBeVisible();
});

test("care report offline restore can reconnect without showing empty state", async ({
  page,
}) => {
  await mockVolunteerApi(page);
  let attempts = 0;
  await page.route("**/v1/line/care-report/drafts/current", async (route) => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 503, body: "offline" });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "draft-a",
        answers: { appetite: "normal" },
        current_step: "observation",
        note: "已保留內容",
      }),
    });
  });

  await page.goto("/care-report");
  await expect(
    page.getByRole("main", { name: "照護回報備援介面" }).getByRole("alert"),
  ).toContainText("目前無法連線");
  await expect(page.getByText("目前沒有可恢復的照護回報")).toHaveCount(0);
  await page.getByRole("button", { name: "重新連線" }).click();
  await expect(page.getByLabel("補充心得（選填）")).toHaveValue("已保留內容");
  expect(attempts).toBe(2);
});

test("saving state disables duplicate submit", async ({ page }) => {
  let saveRequests = 0;
  let releaseSave: () => void = () => undefined;
  const saveGate = new Promise<void>((resolve) => {
    releaseSave = resolve;
  });
  await mockVolunteerApi(page);
  await page.route("**/v1/care-report-drafts/draft-a", async (route) => {
    if (route.request().method() === "PATCH") {
      saveRequests += 1;
      await saveGate;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "draft-a",
          answers: {},
          current_step: "care",
          note: "",
        }),
      });
      return;
    }
    await route.continue();
  });
  await page.goto("/care-report");
  const save = page.locator('button[aria-describedby="save-status"]');
  const requestStarted = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      request.url().endsWith("/v1/care-report-drafts/draft-a"),
  );
  await save.click();
  await requestStarted;
  await expect(save).toBeDisabled();
  await save.click({ force: true });
  releaseSave();
  await expect(
    page.getByText("草稿已保存，可回到 LINE Bot 繼續。"),
  ).toBeVisible();
  expect(saveRequests).toBe(1);
});

test("管理核心清楚區分 no-results、permission denied 與 network error", async ({
  page,
}) => {
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "test-access"),
  );
  await mockManagementApi(page);
  await page.goto("/animals");
  await expect(page.getByText("找不到符合條件的動物")).toBeVisible();

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockManagementApi(page, { animalsStatus: 403 });
  await page.reload();
  await expect(page.getByText("沒有查看權限")).toBeVisible();
  await expect(page.getByText("請切換到已授權收容所")).toBeVisible();

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockManagementApi(page, { reportsStatus: "network" });
  await page.goto("/reports");
  await expect(page.getByText("無法載入 Report Inbox")).toBeVisible();
});

test("管理首頁以 permission denied 與 network error 提供下一步", async ({
  page,
}) => {
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "test-access"),
  );
  await mockManagementApi(page, { dashboardStatus: 403 });
  await page.goto("/");
  await expect(page.getByText("沒有查看權限")).toBeVisible();
  await expect(page.getByText("請切換到已授權收容所")).toBeVisible();

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockManagementApi(page, { dashboardStatus: "network" });
  await page.reload();
  await expect(page.getByText("Dashboard 載入失敗")).toBeVisible();
  await expect(page.getByText(/Dashboard 載入失敗/)).toBeVisible();
});

test("AI processing、ai-failed 與 needs-review 都在 detail 以 polite status 呈現", async ({
  page,
}) => {
  const statuses = [
    { status: "running", label: "AI 處理中" },
    { status: "failed", label: "AI 處理失敗" },
    { status: "succeeded", label: "需要人工覆核" },
  ] as const;

  for (const [index, item] of statuses.entries()) {
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await page.addInitScript(() =>
      sessionStorage.setItem("access_token", "test-access"),
    );
    await mockManagementApi(page, {
      reportDetails: {
        "report-a": {
          id: "report-a",
          animal_id: "animal-a",
          animal_name: "小森",
          status: "saved",
          submitted_at: "2026-08-14T00:00:00Z",
          answers: {},
          note: "原始回報保留",
          media_ids: [],
          ai_observations: [
            {
              id: `observation-${index}`,
              status: item.status,
              source_type: "note",
              raw_ai_output: { text: "原始 AI 輸出" },
              validated_ai_observation: null,
              human_review_result: null,
              failure_reason:
                item.status === "failed" ? "服務暫時無法使用" : null,
            },
          ],
        },
      },
    });
    await page.goto("/reports/report-a");
    const status = page.getByRole("status");
    await expect(status).toHaveAttribute("aria-live", "polite");
    await expect(status).toContainText(item.label);
    if (item.status === "failed") {
      await expect(page.getByText("原始回報保留")).toBeVisible();
      await expect(page.getByText(/原始回報已保存/)).toHaveCount(0);
    }
  }
});

test("login state contract covers credentials, authorization and context failure", async ({
  page,
}) => {
  await mockManagementApi(page);
  await mockLoginApi(page, { loginStatus: 401 });
  await page.goto("/login");
  await page.getByRole("button", { name: "登入" }).click();
  await expect(page.locator("#login-error")).toContainText("登入失敗");

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockLoginApi(page, { organizations: [] });
  await page.reload();
  await page.getByRole("button", { name: "登入" }).click();
  await expect(page.locator("#login-error")).toContainText("沒有收容所授權");

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockLoginApi(page, { contextSwitchStatus: 500 });
  await page.reload();
  await page.getByRole("button", { name: "登入" }).click();
  await expect(page.locator("#login-error")).toContainText("HTTP 500");
});
