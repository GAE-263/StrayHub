import { test, expect } from "@playwright/test";
import { mockManagementApi } from "./fixtures";

test("繁中回報：篩選、原文、追蹤、完成與衝突保留備註", async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  const report = {
    id: "report-a",
    animal_id: "animal-a",
    animal_name: "小黑",
    shelter_number_snapshot: "A023",
    volunteer_label: "王・V003",
    submitted_at: "2026-09-06T08:20:00Z",
    status: "saved",
    ai_job_status: "succeeded",
    note: "右後腳不太敢踩地。",
    story: "今天會主動靠近。",
    answers: { gait: "gait.abnormal" },
    answer_rows: [
      {
        field: "gait",
        label: "走路狀況",
        value: "明顯不對",
        code: "gait.abnormal",
      },
    ],
    summary_status: "succeeded",
    summary: {
      attention_level: "urgent",
      summary: "右後腳不太敢踩地，請人工確認。",
      evidence: [{ field: "note", quote: "右後腳不太敢踩地。" }],
      uncertainties: ["原因尚未確認"],
      information_quality: "clear",
    },
    review_status: "pending",
    review_version: 0,
    review_history: [] as object[],
    media_ids: [],
  };
  await mockManagementApi(page, {
    reports: () => ({ items: [report], total: 1, page: 1, page_size: 20 }),
    reportDetails: { "report-a": report },
  });
  await page.route("**/v1/management/reports/report-a", (route) =>
    route.fulfill({ json: { report } }),
  );
  await page.route(
    "**/v1/management/reports/report-a/processing",
    async (route) => {
      const data = route.request().postDataJSON();
      if (data.expected_version !== report.review_version) {
        await route.fulfill({ status: 409, json: {} });
        return;
      }
      report.review_status = data.status;
      report.review_version++;
      report.review_history.push({
        status: data.status,
        note: data.note,
        at: "2026-09-06T09:00:00Z",
        actor_label: "林管理員",
      });
      await route.fulfill({ json: { report } });
    },
  );
  await page.goto("/reports");
  await page.getByLabel("處理狀態", { exact: true }).selectOption("pending");
  await expect(page.getByText("小黑")).toBeVisible();
  await page.getByRole("link", { name: /小黑/ }).click();
  await expect(
    page.getByRole("heading", { name: "AI 初步整理" }),
  ).toBeVisible();
  await expect(page.getByText("今天會主動靠近。")).toBeVisible();
  await expect(page.locator("pre")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "標記需追蹤" })).toBeDisabled();
  await page.getByLabel("處理備註", { exact: false }).fill("下一班查看右後腳");
  await page.getByRole("button", { name: "標記需追蹤" }).click();
  await expect(
    page.getByRole("heading", { name: "工作人員處理 · 需追蹤" }),
  ).toBeVisible();
  await page
    .getByLabel("處理備註", { exact: false })
    .fill("已查看並告知照護負責人");
  await page.getByRole("button", { name: "追蹤完成", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "工作人員處理 · 追蹤完成" }),
  ).toBeVisible();
  await expect(page.getByText("下一班查看右後腳")).toBeVisible();
  report.review_version++;
  await page.getByLabel("處理備註", { exact: false }).fill("再次查看");
  await page.getByRole("button", { name: "標記需追蹤" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "同事可能已更新" }),
  ).toBeVisible();
  await expect(page.getByLabel("處理備註", { exact: false })).toHaveValue(
    "再次查看",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "工作人員處理 · 追蹤完成" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({
    path: "/tmp/strayhub-report-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({
    path: "/tmp/strayhub-report-desktop.png",
    fullPage: true,
  });
});
