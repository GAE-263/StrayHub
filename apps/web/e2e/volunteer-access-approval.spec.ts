import { expect, test } from "@playwright/test";

test("unknown LINE identity can apply once and reload pending without protected requests", async ({
  page,
}) => {
  let application: { id: string; status: string; version: number } | null =
    null;
  let submitCount = 0;
  const responseBody = () => ({
    organization: { id: "org-a", name: "收容所 A", applications_enabled: true },
    application,
    grant: null,
    effective_status: application ? "pending" : "none",
    next_actions: application ? ["wait", "withdraw"] : ["apply"],
  });
  await page.route("**/v1/volunteer-applications/status", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(responseBody()),
    });
  });
  await page.route("**/v1/volunteer-applications", async (route) => {
    submitCount += 1;
    application ??= { id: "app-a", status: "pending", version: 1 };
    await route.fulfill({
      status: submitCount === 1 ? 201 : 200,
      contentType: "application/json",
      body: JSON.stringify(responseBody()),
    });
  });
  const protectedRequests: string[] = [];
  page.on("request", (request) => {
    if (/\/(animals|care-reports|management)/.test(request.url())) {
      protectedRequests.push(request.url());
    }
  });
  await page.goto(
    "/volunteer-application?entry=local-entry&id_token=local-id-token",
  );
  await expect(page.getByRole("heading", { name: "志工報名" })).toBeVisible();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "立即報名" }).dblclick();
  await expect(page.getByText("等待收容所審核")).toBeVisible();
  expect(submitCount).toBe(1);
  await page.reload();
  await expect(page.getByText("等待收容所審核")).toBeVisible();
  expect(protectedRequests).toEqual([]);
});

test("all-filtered selection preserves the full 1,200 target snapshot", async ({
  page,
}) => {
  let submittedSelection: unknown = null;
  await page.addInitScript(() => {
    window.sessionStorage.setItem("access_token", "local-token");
    window.sessionStorage.setItem("active_organization_id", "org-a");
    window.sessionStorage.setItem("active_organization_code", "ORG-A");
  });
  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url());
    let body: unknown = {};
    let status = 200;
    if (url.pathname.endsWith("/auth/me")) {
      body = {
        user: { id: "admin-a", display_name: "管理員", status: "active" },
        memberships: [
          {
            id: "membership-a",
            organization_id: "org-a",
            role: "SHELTER_ADMIN",
            status: "active",
          },
        ],
      };
    } else if (url.pathname.endsWith("/auth/active-shelter-context")) {
      body = { organization_id: "org-a" };
    } else if (url.pathname === "/v1/organizations") {
      body = { items: [{ id: "org-a", code: "ORG-A", name: "收容所 A" }] };
    } else if (url.pathname.endsWith("/volunteer-applications")) {
      body = {
        items: Array.from({ length: 100 }, (_, index) => ({
          id: `app-${index}`,
          display_name: `志工 ${index}`,
          status: "pending",
          version: 1,
        })),
        matching_count: 1200,
        next_cursor: null,
      };
    } else if (url.pathname.endsWith("/volunteer-decision-batches")) {
      submittedSelection = JSON.parse(
        route.request().postData() ?? "{}",
      ).selection;
      status = 201;
      body = {
        id: "batch-a",
        requested_count: 1200,
        processed_count: 0,
        succeeded_count: 0,
        conflict_count: 0,
        failed_count: 0,
        status: "queued",
      };
    } else if (url.pathname.endsWith("/items")) {
      body = { items: [], next_cursor: null };
    }
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });

  await page.goto("/volunteers/applications");
  await page.getByText("目前篩選結果全部 1,200 筆").click();
  await page.getByRole("button", { name: "確認並建立批次" }).click();
  await page.getByRole("button", { name: "送出完整快照" }).click();
  await expect(page.getByText("批次已建立")).toBeVisible();
  expect(submittedSelection).toEqual({
    mode: "all_filtered",
    filter: { status: "pending" },
  });
});

test("approved volunteer sees finite active period and care handoff", async ({
  page,
}) => {
  await page.route("**/v1/volunteer-applications/status", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        organization: {
          id: "org-a",
          name: "收容所 A",
          applications_enabled: true,
        },
        application: { id: "app-a", status: "approved", version: 2 },
        grant: {
          id: "grant-a",
          status: "active",
          source_type: "manager_approval",
          valid_from: "2026-08-15T04:00:00Z",
          expires_at: "2026-08-22T04:00:00Z",
          version: 1,
        },
        effective_status: "active",
        next_actions: ["enter_care"],
      }),
    });
  });
  await page.goto(
    "/volunteer-application?entry=local-entry&id_token=local-id-token",
  );
  await expect(page.getByText("志工授權使用中")).toBeVisible();
  await expect(page.getByText("授權期間（台灣時間）")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "進入照護流程" }),
  ).toHaveAttribute("href", "/animal-confirmation");
});

test("shelter admin can revoke an active grant with a reason", async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.sessionStorage.setItem("access_token", "local-token");
    window.sessionStorage.setItem("active_organization_id", "org-a");
    window.sessionStorage.setItem("active_organization_code", "ORG-A");
  });
  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url());
    let body: unknown = {};
    if (url.pathname.endsWith("/auth/me")) {
      body = {
        user: { id: "admin-a", display_name: "管理員", status: "active" },
        memberships: [
          {
            id: "membership-a",
            organization_id: "org-a",
            role: "SHELTER_ADMIN",
            status: "active",
          },
        ],
      };
    } else if (url.pathname.endsWith("/auth/active-shelter-context")) {
      body = { organization_id: "org-a" };
    } else if (url.pathname === "/v1/organizations") {
      body = { items: [{ id: "org-a", code: "ORG-A", name: "收容所 A" }] };
    } else if (url.pathname.endsWith("/volunteer-access-grants")) {
      body = {
        items: [
          {
            id: "grant-a",
            display_name: "志工 A",
            status: "active",
            source_type: "manager_approval",
            valid_from: "2026-08-15T04:00:00Z",
            expires_at: "2027-08-22T04:00:00Z",
            version: 1,
          },
        ],
        next_cursor: null,
      };
    } else if (url.pathname.endsWith("/volunteer-access-grants/grant-a")) {
      body = {
        id: "grant-a",
        display_name: "志工 A",
        status: "revoked",
        source_type: "manager_approval",
        valid_from: "2026-08-15T04:00:00Z",
        expires_at: "2027-08-22T04:00:00Z",
        version: 2,
        revocation_reason: "排班異動",
      };
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  await page.goto("/volunteers/access");
  await page.getByLabel("志工 A 操作原因").fill("排班異動");
  await page.getByRole("button", { name: "撤銷授權" }).click();
  await page.getByRole("button", { name: "確認調整" }).click();
  await expect(page.getByText("已撤銷「志工 A」的志工授權")).toBeVisible();
  await expect(page.getByText("歷史週期（不可修改）")).toBeVisible();
});

test("STAFF deep link does not mount volunteer management request", async ({
  page,
}) => {
  let managementRequests = 0;
  await page.addInitScript(() => {
    window.sessionStorage.setItem("access_token", "local-token");
    window.sessionStorage.setItem("active_organization_id", "org-a");
    window.sessionStorage.setItem("active_organization_code", "ORG-A");
  });
  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.includes("/volunteer-notifications"))
      managementRequests += 1;
    let body: unknown = {};
    if (url.pathname.endsWith("/auth/me")) {
      body = {
        user: { id: "staff-a", display_name: "工作人員", status: "active" },
        memberships: [
          {
            id: "membership-a",
            organization_id: "org-a",
            role: "STAFF",
            status: "active",
          },
        ],
      };
    } else if (url.pathname.endsWith("/auth/active-shelter-context")) {
      body = { organization_id: "org-a" };
    } else if (url.pathname === "/v1/organizations") {
      body = { items: [{ id: "org-a", code: "ORG-A", name: "收容所 A" }] };
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  await page.goto("/volunteers/notifications");
  await expect(page.getByText("無法開啟志工管理")).toBeVisible();
  expect(managementRequests).toBe(0);
});
