import { expect, test, type Page } from "@playwright/test";
import { mockManagementApi } from "./fixtures";

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
