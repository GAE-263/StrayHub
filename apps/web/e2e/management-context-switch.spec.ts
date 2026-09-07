import { expect, test, type Page } from "@playwright/test";
import { mockManagementApi, type GrowthDiaryFixtureItem } from "./fixtures";

async function setup(
  page: Page,
  failure: boolean | "lost-response" | "unavailable" = false,
) {
  let active = "org-a";
  let attempted = false;
  const foreignRequests: string[] = [];
  const organizations = ["a", "b", "c"].map((id) => ({
    id: `org-${id}`,
    code: `ORG-${id.toUpperCase()}`,
    name: `Shelter ${id}`,
    role: "SHELTER_ADMIN",
    status: "active",
    timezone: "Asia/Taipei",
    timezone_version: 1,
  }));
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "test-access"),
  );
  await mockManagementApi(page, {
    organizations,
    animals: () => ({
      items: [
        {
          id: `animal-${active}`,
          name: `Animal ${active}`,
          shelter_number: `${active}-001`,
          organization_id: active,
          status: "active",
        },
      ],
      page: 1,
      page_size: 20,
      total: 1,
    }),
  });
  await page.route("**/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/v1/auth/active-shelter-context") {
      if (request.method() === "PUT") {
        attempted = true;
        if (!failure || failure === "lost-response")
          active = request.postDataJSON().organization_id;
        if (failure === "lost-response" || failure === "unavailable") {
          await route.abort("failed");
          return;
        }
      }
      await route.fulfill({
        status:
          attempted && failure === "unavailable"
            ? 503
            : request.method() === "PUT" && failure
              ? 500
              : 200,
        json: {
          organization_id: active,
          organization_name: `Shelter ${active.slice(-1)}`,
        },
      });
      return;
    }
    if (
      active !== "org-a" &&
      (url.pathname.includes("animal-a") ||
        url.searchParams.get("animal_id") === "animal-a")
    ) {
      foreignRequests.push(url.pathname + url.search);
      await route.fulfill({ status: 404, json: { detail: "not found" } });
      return;
    }
    await route.fallback();
  });
  return { foreignRequests };
}

for (const path of ["/animals/animal-a", "/animals/animal-a/timeline"]) {
  test(`switch from ${path} never reuses A animal under B context`, async ({
    page,
  }) => {
    const { foreignRequests } = await setup(page);
    await page.goto(path);
    await expect(
      page.getByRole("heading", {
        name: path.endsWith("timeline") ? "動物近期歷程" : "小森",
        exact: true,
      }),
    ).toBeVisible();
    await page.getByLabel("切換目前收容所").selectOption("org-b");
    await expect(page.getByLabel("切換目前收容所")).toHaveValue("org-b");
    await expect(page).toHaveURL(/\/animals$/);
    await expect(
      page.getByRole("link", { name: "Animal org-b", exact: true }),
    ).toBeVisible();
    expect(foreignRequests).toEqual([]);
    await expect(
      page.getByRole("heading", { name: "動物近期歷程", exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("heading", { name: "照護 QR Code", exact: true }),
    ).toHaveCount(0);
    await page.getByLabel("切換目前收容所").selectOption("org-c");
    await expect(
      page.getByRole("link", { name: "Animal org-c", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Animal org-b", exact: true }),
    ).toHaveCount(0);
    expect(foreignRequests).toEqual([]);
  });
}

test("failed context switch restores A detail without mixed context", async ({
  page,
}) => {
  const { foreignRequests } = await setup(page, true);
  await page.goto("/animals/animal-a");
  await expect(
    page.getByRole("heading", { name: "小森", exact: true }),
  ).toBeVisible();
  await page.getByLabel("切換目前收容所").selectOption("org-b");
  await expect(
    page.getByText("無法切換目前收容所", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("切換目前收容所")).toHaveValue("org-a");
  await expect(page).toHaveURL(/\/animals\/animal-a$/);
  await expect(
    page.getByRole("heading", { name: "小森", exact: true }),
  ).toBeVisible();
  expect(foreignRequests).toEqual([]);
});

test("all animal panels unmount before the context PUT finishes", async ({
  page,
}) => {
  const { foreignRequests } = await setup(page);
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let started = false;
  await page.route("**/v1/auth/active-shelter-context", async (route) => {
    if (route.request().method() === "PUT") {
      started = true;
      await held;
    }
    await route.fallback();
  });
  await page.goto("/animals/animal-a/timeline");
  await expect(
    page.getByRole("heading", { name: "動物近期歷程", exact: true }),
  ).toBeVisible();
  await page.getByLabel("切換目前收容所").selectOption("org-b");
  await expect.poll(() => started).toBe(true);
  await expect(
    page.getByRole("heading", { name: "動物近期歷程", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText("醫療歷史", { exact: true })).toHaveCount(0);
  await expect(
    page.getByText("正在確認工作台權限…", { exact: true }),
  ).toBeVisible();
  release();
  await expect(
    page.getByRole("link", { name: "Animal org-b", exact: true }),
  ).toBeVisible();
  expect(foreignRequests).toEqual([]);
});

test("lost success response reconciles committed B instead of restoring A detail", async ({
  page,
}) => {
  const { foreignRequests } = await setup(page, "lost-response");
  await page.goto("/animals/animal-a");
  await expect(
    page.getByRole("heading", { name: "小森", exact: true }),
  ).toBeVisible();
  await page.getByLabel("切換目前收容所").selectOption("org-b");
  await expect(page).toHaveURL(/\/animals$/);
  await expect(
    page.getByRole("link", { name: "Animal org-b", exact: true }),
  ).toBeVisible();
  expect(foreignRequests).toEqual([]);
});

test("unverifiable context stays blocked instead of remounting an old detail", async ({
  page,
}) => {
  await setup(page, "unavailable");
  await page.goto("/animals/animal-a");
  await expect(
    page.getByRole("heading", { name: "小森", exact: true }),
  ).toBeVisible();
  await page.getByLabel("切換目前收容所").selectOption("org-b");
  await expect(
    page.getByRole("button", { name: "重新確認收容所", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "小森", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByLabel("切換目前收容所")).toHaveCount(0);
});

test("late A timeline/medical responses cannot populate B list", async ({
  page,
}) => {
  const { foreignRequests } = await setup(page);
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let pending = 0;
  await page.route(
    /\/v1\/(?:animals\/animal-a\/timeline|management\/animals\/animal-a\/medical-records)/,
    async (route) => {
      pending += 1;
      await held;
      await route
        .fulfill({ json: { days: [], items: [], total_count: 0 } })
        .catch(() => undefined);
    },
  );
  await page.goto("/animals/animal-a/timeline");
  await expect.poll(() => pending).toBeGreaterThanOrEqual(2);
  const beforeSwitch = pending; // React StrictMode may mount effects twice.
  await page.getByLabel("切換目前收容所").selectOption("org-b");
  await expect(page).toHaveURL(/\/animals$/);
  release();
  await expect(
    page.getByRole("link", { name: "Animal org-b", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "動物近期歷程", exact: true }),
  ).toHaveCount(0);
  expect(pending).toBe(beforeSwitch);
  expect(foreignRequests).toEqual([]);
});

function diaryItem(
  organizationId: string,
  suffix: string,
  hasPhoto: boolean,
): GrowthDiaryFixtureItem {
  return {
    id: `00000000-0000-4000-8000-0000000000${suffix}`,
    inquiry_id: "10000000-0000-4000-8000-000000000001",
    animal_id: "20000000-0000-4000-8000-000000000001",
    animal_name: `${organizationId} 毛孩 ${suffix}`,
    shelter_number: `${organizationId}-${suffix}`,
    has_photo: hasPhoto,
    photo_endpoint: hasPhoto
      ? `/v1/management/growth-diary-entries/00000000-0000-4000-8000-0000000000${suffix}/photo`
      : null,
    photo_endpoints: hasPhoto
      ? [
          `/v1/management/growth-diary-entries/00000000-0000-4000-8000-0000000000${suffix}/photos/0`,
        ]
      : [],
    note: `${organizationId} diary text ${suffix}`,
    status: "new",
    status_updated_at: null,
    entry_date: "2026-09-01",
    ai_analysis: {
      status: "succeeded",
      provenance_status: "available",
      mood: "neutral",
      adopter_reply: "謝謝分享。",
      staff_summary: `${organizationId} summary`,
    },
    created_at: "2026-09-01T10:00:00Z",
  };
}

test("delayed A diary JSON and Blob lifecycles cannot publish after switching to B or re-login", async ({
  page,
}) => {
  const events: string[] = [];
  const failedDiaryRequests: string[] = [];
  page.on("requestfailed", (request) => {
    if (request.url().includes("/growth-diary-entries/")) {
      failedDiaryRequests.push(new URL(request.url()).pathname);
    }
  });
  const organizations = ["a", "b"].map((id) => ({
    id: `org-${id}`,
    code: `ORG-${id.toUpperCase()}`,
    name: `Shelter ${id.toUpperCase()}`,
    role: "SHELTER_ADMIN",
    status: "active",
    timezone: "Asia/Taipei",
    timezone_version: 1,
  }));
  await page.addInitScript(() => {
    if (sessionStorage.getItem("e2e_skip_auto_auth") !== "1") {
      sessionStorage.setItem("access_token", "test-access");
    }
    const originalRevoke = URL.revokeObjectURL.bind(URL);
    URL.revokeObjectURL = (url: string) => {
      const count = Number(sessionStorage.getItem("diary_revoke_count") ?? 0);
      sessionStorage.setItem("diary_revoke_count", String(count + 1));
      originalRevoke(url);
    };
  });
  await mockManagementApi(page, {
    organizations,
    platformRole: null,
    growthDiaryEvents: events,
    growthDiaryEntries: (_params, organizationId) => {
      const items =
        organizationId === "org-a"
          ? [diaryItem("org-a", "11", true), diaryItem("org-a", "12", true)]
          : [diaryItem("org-b", "21", false)];
      return {
        items,
        page: 1,
        page_size: 20,
        total: items.length,
        timezone: "Asia/Taipei",
      };
    },
    growthDiaryPhotoDelay: (entryId, organizationId) =>
      organizationId === "org-a" && entryId.endsWith("12") ? 3_000 : 0,
    growthDiaryDetailDelay: (_entryId, organizationId) =>
      organizationId === "org-a" ? 3_000 : 0,
  });

  await page.goto("/growth-diary");
  await expect(page.getByText("org-a diary text 11")).toBeVisible();
  await expect.poll(() => events).toContain("photo:finish:org-a");
  await expect.poll(() => events).toContain("photo:start:org-a");
  await page.getByRole("button", { name: "查看 AI 來源" }).first().click();
  await expect.poll(() => events).toContain("detail:start:org-a");

  await page.getByLabel("切換目前收容所").selectOption("org-b");
  await expect(page.getByText("org-a diary text 11")).toHaveCount(0);
  await expect(page).toHaveURL(/\/animals$/);
  await expect
    .poll(() =>
      page.evaluate(() =>
        Number(sessionStorage.getItem("diary_revoke_count") ?? 0),
      ),
    )
    .toBeGreaterThanOrEqual(1);
  await expect
    .poll(() => failedDiaryRequests.some((path) => path.endsWith("/photo")), {
      timeout: 7_000,
    })
    .toBe(true);
  await expect
    .poll(
      () =>
        failedDiaryRequests.some(
          (path) =>
            path.includes("/growth-diary-entries/") && !path.endsWith("/photo"),
        ),
      { timeout: 7_000 },
    )
    .toBe(true);

  await page.goto("/growth-diary");
  await expect(page.getByText("org-b diary text 21")).toBeVisible();
  await expect(page.getByText(/org-a diary text/)).toHaveCount(0);

  await page.evaluate(() => {
    sessionStorage.setItem("e2e_skip_auto_auth", "1");
    sessionStorage.removeItem("access_token");
  });
  await page.reload();
  await expect(page).toHaveURL(/\/login$/);
  await page.evaluate(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.removeItem("e2e_skip_auto_auth");
  });
  await page.goto("/growth-diary");
  await expect(page.getByText("org-b diary text 21")).toBeVisible();
  await expect(page.getByText(/org-a diary text/)).toHaveCount(0);
});
