import { expect, test, type Page } from "@playwright/test";

const organizationId = "11111111-1111-4111-8111-111111111111";

async function mockStatusApis(page: Page, withApplication = false) {
  await page.route("**/v1/public/volunteer-organizations", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        regions: [
          {
            name: "新北市",
            organizations: [
              {
                id: organizationId,
                name: "新北市新店區公立動物之家",
                address: "新北市新店區",
              },
            ],
          },
        ],
      }),
    });
  });
  await page.route(
    "**/v1/volunteer-applications/self-status",
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: withApplication
            ? [
                {
                  organization: {
                    id: organizationId,
                    name: "新北市新店區公立動物之家",
                    address: "新北市新店區",
                  },
                  application: {
                    id: "application-a",
                    organization_id: organizationId,
                    display_name: "LINE 志工",
                    status: "pending",
                    submitted_at: "2026-08-27T01:00:00Z",
                    version: 1,
                  },
                  service_dates: [
                    {
                      service_date: "2026-09-01",
                      status: "pending",
                      decided_at: null,
                      decision_reason: null,
                      version: 1,
                    },
                  ],
                  grant: null,
                  effective_status: "pending",
                },
              ]
            : [],
        }),
      });
    },
  );
}

test("direct and encoded LIFF status intents open the dedicated empty state", async ({
  page,
}) => {
  await mockStatusApis(page);
  for (const query of [
    "view=status",
    `liff.state=${encodeURIComponent("?view=status")}`,
  ]) {
    await page.goto(`/volunteer-application?${query}`);
    await expect(
      page.getByRole("heading", { name: "我的志工申請" }),
    ).toBeVisible();
    await expect(page.getByText("目前沒有志工申請紀錄")).toBeVisible();
    await expect(page.getByText("選擇想服務的地區")).toHaveCount(0);
  }
});

test("status shows an organization-scoped application and can start another", async ({
  page,
}) => {
  await mockStatusApis(page, true);
  await page.goto(
    `/volunteer-application?view=status&organization_id=${organizationId}`,
  );
  await expect(page.getByText("新北市新店區公立動物之家")).toBeVisible();
  await expect(page.getByText("審核中")).toBeVisible();
  await page.getByRole("button", { name: "前往其他收容所報名" }).click();
  await expect(page.getByText("選擇想服務的地區")).toBeVisible();
});

test("empty status changes to signup only after the explicit action", async ({
  page,
}) => {
  await mockStatusApis(page);
  await page.goto("/volunteer-application?view=status");
  await expect(page.getByText("目前沒有志工申請紀錄")).toBeVisible();
  await expect(page.getByText("選擇想服務的地區")).toHaveCount(0);
  await page.getByRole("button", { name: "前往志工報名" }).click();
  await expect(page.getByText("選擇想服務的地區")).toBeVisible();
  await expect(page).toHaveURL(/\/volunteer-application$/);
});

test("the general shared LIFF still opens the application directory", async ({
  page,
}) => {
  await mockStatusApis(page);
  await page.goto("/volunteer-application");
  await expect(page.getByText("選擇想服務的地區")).toBeVisible();
  await expect(page.getByRole("heading", { name: "我的志工申請" })).toHaveCount(
    0,
  );
});
