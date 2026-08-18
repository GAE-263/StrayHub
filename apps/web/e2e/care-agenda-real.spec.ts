import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { seedMedicalCareFixture } from "./fixtures/medical-care";

type Bucket =
  "today_pending" | "overdue" | "today_resolved" | "next_seven_days";

type AgendaManifest = {
  items: Array<{
    bucket: Bucket;
    animal_name: string;
    shelter_number: string;
    title: string;
    reminder_type: string;
    status: string;
  }>;
  buckets: Record<Bucket, { total: number; occurrence_ids: string[] }>;
};

const bucketLabels: Record<Bucket, string> = {
  today_pending: "今天待處理",
  overdue: "已逾期",
  today_resolved: "今天已完成／略過／取消",
  next_seven_days: "未來七天",
};

test.describe("Care Agenda 真實 API 100／500 驗收", () => {
  test.skip(
    process.env.STRAYHUB_MEDICAL_E2E_SEED_ALLOWED !== "1",
    "僅在 loopback test DB 明確 opt-in 時執行",
  );

  test("所有 occurrence 可走完分頁且與 manifest 分類完全一致", async ({
    page,
  }, testInfo) => {
    test.setTimeout(120_000);
    const fixture = await seedMedicalCareFixture(page);
    try {
      const manifest = JSON.parse(
        await readFile(fixture.manifest, "utf8"),
      ) as AgendaManifest;
      const observed = Object.fromEntries(
        Object.keys(bucketLabels).map((bucket) => [bucket, new Set<string>()]),
      ) as Record<Bucket, Set<string>>;
      const responseReads: Array<Promise<void>> = [];
      page.on("response", (response) => {
        if (
          response.ok() &&
          new URL(response.url()).pathname === "/v1/management/care-agenda"
        ) {
          responseReads.push(
            response.json().then((body) => {
              for (const bucket of Object.keys(bucketLabels) as Bucket[]) {
                for (const item of body.buckets[bucket] ?? []) {
                  observed[bucket].add(item.occurrence_id);
                }
              }
            }),
          );
        }
      });

      await page.goto("/login");
      await page.getByLabel("帳號").fill("local-staff-a");
      await page.getByLabel("密碼").fill("local-only-password");
      await page.getByRole("button", { name: "登入" }).click();
      await expect(page).toHaveURL(/\/$/);
      await page.goto("/care-calendar");
      await expect(
        page.getByRole("heading", { name: "照護行事曆" }),
      ).toBeVisible();

      const startedAt = performance.now();
      for (const bucket of Object.keys(bucketLabels) as Bucket[]) {
        const region = page.getByRole("region", {
          name: bucketLabels[bucket],
          exact: true,
        });
        await expect(region.getByRole("article").first()).toBeVisible();
        for (let pageNumber = 0; pageNumber < 20; pageNumber += 1) {
          const loadMore = region.getByRole("button", { name: /載入更多/ });
          if ((await loadMore.count()) === 0) break;
          await loadMore.click();
          await expect(region.getByText("正在載入更多…")).toHaveCount(0);
        }
        await expect(region.getByRole("article")).toHaveCount(
          manifest.buckets[bucket].total,
        );
      }
      const elapsedMs = performance.now() - startedAt;
      await Promise.all(responseReads);

      for (const bucket of Object.keys(bucketLabels) as Bucket[]) {
        expect([...observed[bucket]].sort()).toEqual(
          [...manifest.buckets[bucket].occurrence_ids].sort(),
        );
      }

      for (const item of manifest.items) {
        const region = page.getByRole("region", {
          name: bucketLabels[item.bucket],
          exact: true,
        });
        const card = region
          .getByRole("article")
          .filter({ has: page.getByText(item.title, { exact: true }) })
          .filter({ hasText: item.shelter_number });
        await expect(card).toHaveCount(1);
        await expect(card).toContainText(item.animal_name);
        await expect(card).toContainText(item.reminder_type);
        await expect(card).toContainText(item.status);
      }

      const classificationEvidence = {
        elapsed_ms: Number(elapsedMs.toFixed(3)),
        totals: Object.fromEntries(
          (Object.keys(bucketLabels) as Bucket[]).map((bucket) => [
            bucket,
            observed[bucket].size,
          ]),
        ),
        missing: 0,
        unexpected: 0,
        classification_pass_rate: 1,
      };
      console.log(
        `[T097 agenda-500] ${JSON.stringify(classificationEvidence)}`,
      );
      await testInfo.attach("care-agenda-500-classification.json", {
        body: JSON.stringify(classificationEvidence, null, 2),
        contentType: "application/json",
      });
    } finally {
      await fixture.cleanup();
    }
  });
});
