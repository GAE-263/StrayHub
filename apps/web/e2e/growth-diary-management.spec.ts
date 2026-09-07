import { expect, test, type Page } from "@playwright/test";
import {
  mockManagementApi,
  type GrowthDiaryFixtureItem,
  type ManagementFixtureOptions,
} from "./fixtures";

const item: GrowthDiaryFixtureItem = {
  id: "00000000-0000-4000-8000-000000000010",
  inquiry_id: "10000000-0000-4000-8000-000000000010",
  animal_id: "20000000-0000-4000-8000-000000000010",
  animal_name: "米糕",
  shelter_number: "A-102",
  has_photo: false,
  photo_endpoint: null,
  photo_endpoints: [],
  note: "今天願意吃晚餐。",
  status: "new",
  status_updated_at: null,
  entry_date: "2026-09-01",
  ai_analysis: {
    status: "succeeded",
    provenance_status: "available",
    mood: "concern",
    adopter_reply: "謝謝分享。",
    staff_summary: "食慾仍需留意。",
  },
  created_at: "2026-09-01T10:00:00Z",
};

async function authorize(page: Page) {
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "test-access"),
  );
}

test("list keeps raw output lazy and loads authenticated WebP with safe headers", async ({
  page,
}) => {
  await authorize(page);
  await mockManagementApi(page);
  const listResponse = page.waitForResponse((response) =>
    response
      .url()
      .endsWith("/v1/management/growth-diary-entries?page=1&page_size=20"),
  );
  const photoResponse = page.waitForResponse((response) =>
    response.url().endsWith("/photo"),
  );

  await page.goto("/growth-diary");
  const listBody = await (await listResponse).json();
  expect(JSON.stringify(listBody)).not.toContain("ai_raw_output");
  await expect(page.getByRole("heading", { name: "毛孩日記" })).toBeVisible();
  await expect(page.getByText("org-a 的近況文字")).toBeVisible();
  await expect(page.getByText("AI 原始輸出")).toHaveCount(0);

  const photo = await photoResponse;
  expect(photo.headers()["content-type"]).toContain("image/webp");
  expect(photo.headers()["cache-control"]).toBe("private, no-store");
  expect(photo.headers()["x-content-type-options"]).toBe("nosniff");

  await page.getByRole("button", { name: "查看 AI 來源" }).first().click();
  await expect(page.getByText("AI 原始輸出")).toBeVisible();
  await expect(page.getByText(/growth-diary-v1/)).toBeVisible();
});

test("search, mood filter, filtered empty, clear, and pagination stay server-side", async ({
  page,
}) => {
  await authorize(page);
  const seen: string[] = [];
  await mockManagementApi(page, {
    growthDiaryEntries: (params) => {
      seen.push(params.toString());
      const filtered = Boolean(params.get("query") || params.get("mood"));
      return {
        items: filtered ? [] : [item],
        page: Number(params.get("page") ?? 1),
        page_size: Number(params.get("page_size") ?? 20),
        total: filtered ? 0 : 21,
        timezone: "Asia/Taipei",
      };
    },
  });
  await page.goto("/growth-diary");
  await expect(page.getByText("米糕", { exact: true })).toBeVisible();

  await page.getByLabel("動物名稱或收容編號").fill("  花花  ");
  await page.getByLabel("關注狀態").selectOption("concern");
  await page.getByRole("button", { name: "搜尋", exact: true }).click();
  await expect(page.getByText("找不到符合條件的日記")).toBeVisible();
  expect(seen.at(-1)).toContain("query=%E8%8A%B1%E8%8A%B1");
  expect(seen.at(-1)).toContain("mood=concern");
  expect(seen.at(-1)).toContain("page=1");

  await page.getByRole("button", { name: "清除搜尋與篩選" }).click();
  await expect(page.getByText("米糕", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "下一頁" }).click();
  expect(seen.at(-1)).toContain("page=2");
});

const roleFixtures: Array<{
  name: string;
  options: ManagementFixtureOptions;
}> = [
  { name: "STAFF", options: {} },
  {
    name: "SHELTER_ADMIN",
    options: {
      platformRole: null,
      organizations: [
        {
          id: "org-a",
          code: "ORG-A",
          name: "Shelter A",
          role: "SHELTER_ADMIN",
          status: "active",
          timezone: "Asia/Taipei",
          timezone_version: 1,
        },
      ],
    },
  },
  { name: "PLATFORM_ADMIN", options: { platformRole: "PLATFORM_ADMIN" } },
];

for (const fixture of roleFixtures) {
  test(`${fixture.name} with an active shelter context can read the diary`, async ({
    page,
  }) => {
    await authorize(page);
    await mockManagementApi(page, fixture.options);
    await page.goto("/growth-diary");
    await expect(page.getByText("org-a 的近況文字")).toBeVisible();
  });
}

test("denied role receives a safe 403 state", async ({ page }) => {
  await authorize(page);
  await mockManagementApi(page, {
    platformRole: null,
    organizations: [
      {
        id: "org-a",
        code: "ORG-A",
        name: "Shelter A",
        role: "VOLUNTEER",
        status: "active",
        timezone: "Asia/Taipei",
        timezone_version: 1,
      },
    ],
    growthDiaryStatus: 403,
  });
  await page.goto("/growth-diary");
  await expect(page.getByText("沒有查看毛孩日記的權限")).toBeVisible();
  await expect(page.getByText("org-a 的近況文字")).toHaveCount(0);
});

test("missing active shelter context blocks the feature before diary data is shown", async ({
  page,
}) => {
  await authorize(page);
  await mockManagementApi(page, { noActiveOrganizationContext: true });
  await page.goto("/growth-diary");
  await expect(page.getByText("無法開啟管理工作台")).toBeVisible();
  await expect(page.getByText("org-a 的近況文字")).toHaveCount(0);
});

test("network failure remains empty and retry creates a new request", async ({
  page,
}) => {
  await authorize(page);
  let attempts = 0;
  await mockManagementApi(page, {
    growthDiaryStatus: () => (++attempts <= 2 ? "network" : 200),
  });
  await page.goto("/growth-diary");
  await expect(page.getByText("目前無法載入毛孩日記")).toBeVisible();
  await page.getByRole("button", { name: "重新載入" }).click();
  await expect(page.getByText("org-a 的近況文字")).toBeVisible();
  expect(attempts).toBeGreaterThanOrEqual(2);
});
