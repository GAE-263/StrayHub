import { expect, test } from "@playwright/test";
import {
  mockLiffBrowser,
  mockVolunteerAccessApi,
} from "./volunteer-access-fixtures";

test("context switch rejects organizations without an active membership", async ({
  page,
}) => {
  await mockVolunteerAccessApi(page, {
    organizations: [
      { id: "org-a", code: "ORG-A", name: "收容所 A" },
      { id: "org-b", code: "ORG-B", name: "收容所 B" },
    ],
    activeOrganizationId: "org-a",
    memberships: [
      {
        id: "membership-a",
        organization_id: "org-a",
        role: "SHELTER_ADMIN",
        status: "active",
      },
      {
        id: "membership-b",
        organization_id: "org-b",
        role: "SHELTER_ADMIN",
        status: "suspended",
      },
    ],
  });
  await page.goto("/");

  const result = await page.evaluate(async () => {
    const response = await fetch("/v1/auth/active-shelter-context", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ organization_id: "org-b" }),
    });
    return { status: response.status, body: await response.json() };
  });

  expect(result.status).toBe(403);
  expect(result.body.organization_id).toBe("org-a");
});

test("unknown LINE identity reaches NEW then PENDING without protected requests", async ({
  page,
}, testInfo) => {
  let application: { id: string; status: string; version: number } | null =
    null;
  let submitCount = 0;

  const responseBody = () => ({
    organization: {
      id: "org-a",
      name: "收容所 A",
      applications_enabled: true,
      insurance_required: false,
    },
    application,
    grant: null,
    effective_status: application ? "pending" : "none",
    next_actions: application ? ["wait", "withdraw"] : ["apply"],
  });
  await page.route("**/v1/auth/liff/exchange", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        state: application ? "PENDING" : "NEW",
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
  await mockLiffBrowser(page);
  await page.goto(
    "/volunteer-entry?entry=opaque-entry-reference-0123456789abcdef-extra",
  );
  await expect(
    page.getByRole("heading", { name: "尚未完成志工報名" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 360, height: 800 });
  await page.locator("nextjs-portal").evaluateAll((portals) => {
    portals.forEach((portal) => {
      (portal as HTMLElement).style.display = "none";
    });
  });
  await page.screenshot({
    path: testInfo.outputPath("ft022-volunteer-application-360.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "進入志工報名" }).click();
  await expect(page.getByRole("heading", { name: "志工報名" })).toBeVisible();
  await page.locator("#applicant-name").fill("王小明");
  await page.locator("#phone-number").fill("0912345678");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "立即報名" }).dblclick();
  await expect(page.getByText("等待收容所審核")).toBeVisible();
  expect(submitCount).toBe(1);
  await page.reload();
  await expect(page.getByRole("status")).toContainText(
    "申請已送出，請耐心等候收容所工作人員審核。",
  );
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
  await page.route("**/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user: { id: "volunteer-a", display_name: "志工", status: "active" },
        memberships: [
          {
            id: "membership-a",
            organization_id: "org-a",
            role: "VOLUNTEER",
            status: "active",
            valid_from: "2020-01-01T00:00:00Z",
            expires_at: "2050-01-01T00:00:00Z",
            access_grant: {
              membership_id: "membership-a",
              organization_id: "org-a",
              status: "active",
              valid_from: "2020-01-01T00:00:00Z",
              expires_at: "2050-01-01T00:00:00Z",
            },
          },
        ],
      }),
    });
  });
  await page.route("**/v1/auth/active-shelter-context", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        organization_id: "org-a",
        organization_name: "收容所 A",
      }),
    });
  });
  await page.route("**/v1/organizations", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [{ id: "org-a", code: "ORG-A", name: "收容所 A" }],
      }),
    });
  });
  await page.route("**/v1/auth/liff/exchange", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        state: "ACTIVE",
        access_token: "active-access-token",
        refresh_token: "active-refresh-token",
        session_id: "session-a",
        organization: {
          id: "org-a",
          code: "ORG-A",
          name: "收容所 A",
        },
        user: { role: "VOLUNTEER" },
      }),
    });
  });
  await page.route("**/v1/animals**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "animal-a",
            name: "小森",
            shelter_number: "A-001",
            organization_id: "org-a",
            can_report: true,
          },
        ],
      }),
    });
  });
  await mockLiffBrowser(page);
  await page.goto(
    "/volunteer-entry?entry=opaque-entry-reference-0123456789abcdef-extra",
  );
  await expect(
    page.getByRole("heading", { name: "選擇照護動物" }),
  ).toBeVisible();
  await expect(page.getByText("小森／A-001")).toBeVisible();
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
