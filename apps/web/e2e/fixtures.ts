import type { Page, Route } from "@playwright/test";

const organization = {
  id: "org-a",
  code: "ORG-A",
  name: "浪浪森友會 A",
  role: "STAFF",
  status: "active",
  timezone: "Asia/Taipei",
  timezone_version: 1,
};

type FixtureStatus = number | "network";

type AnimalFixture = {
  id: string;
  name: string;
  shelter_number: string;
  status?: string;
  area_name?: string | null;
  area_type?: string | null;
  can_report?: boolean;
  organization_id?: string;
};

type ReportFixture = {
  id: string;
  animal_id: string;
  animal_name: string | null;
  status: string;
  ai_job_status: string;
  submitted_at: string;
  note: string | null;
};

type ListResponse<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
};

export type ManagementFixtureOptions = {
  organizations?: (typeof organization)[];
  activeOrganizationId?: string;
  memberships?: Array<{
    id: string;
    organization_id: string;
    role: string;
    status: string;
  }>;
  contextSwitchStatus?: number;
  dashboardStatus?: FixtureStatus;
  dashboard?: Record<string, unknown>;
  animalsStatus?: FixtureStatus;
  animals?: (params: URLSearchParams) => ListResponse<AnimalFixture>;
  animalDelay?: (params: URLSearchParams) => number;
  areas?: Array<{ id: string; name: string; area_type: string }>;
  reportsStatus?: FixtureStatus;
  reports?: (params: URLSearchParams) => ListResponse<ReportFixture>;
  reportDelay?: (params: URLSearchParams) => number;
  animalDetailStatus?: FixtureStatus;
  animalDetails?: Record<string, unknown>;
  reportDetailStatus?: FixtureStatus;
  reportDetails?: Record<string, unknown>;
  timelineStatus?: FixtureStatus;
  timelines?: (animalId: string, params: URLSearchParams) => unknown;
  timelineDelay?: (animalId: string, params: URLSearchParams) => number;
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function respond(
  route: Route,
  body: unknown,
  status: FixtureStatus = 200,
  delay = 0,
) {
  if (status === "network") {
    await route.abort("failed");
    return;
  }
  if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
  await json(route, body, status);
}

export async function mockManagementApi(
  page: Page,
  options: ManagementFixtureOptions = {},
) {
  const organizations = options.organizations ?? [organization];
  let activeOrganizationId =
    options.activeOrganizationId ?? organizations[0]?.id ?? organization.id;
  const memberships =
    options.memberships ??
    organizations.map((item, index) => ({
      id: `membership-${item.id}`,
      organization_id: item.id,
      role: item.role,
      status: item.status,
      ...(index === 0 ? {} : {}),
    }));
  const contextSwitchStatus = options.contextSwitchStatus ?? 200;
  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/auth/me")) {
      await json(route, {
        user: {
          id: "user-a",
          username: "local-staff-a",
          display_name: "林工作人員",
          platform_role: "STAFF",
          status: "active",
        },
        memberships,
      });
      return;
    }
    if (url.pathname.endsWith("/auth/active-shelter-context")) {
      if (route.request().method() === "PUT") {
        const body = route.request().postDataJSON() as {
          organization_id?: string;
        };
        const requestedOrganizationId = body.organization_id;
        const canSwitch =
          typeof requestedOrganizationId === "string" &&
          organizations.some((item) => item.id === requestedOrganizationId) &&
          memberships.some(
            (membership) =>
              membership.organization_id === requestedOrganizationId &&
              membership.status === "active",
          );
        if (canSwitch && requestedOrganizationId) {
          activeOrganizationId = requestedOrganizationId;
        }
        const activeOrganization =
          organizations.find((item) => item.id === activeOrganizationId) ??
          organization;
        await json(
          route,
          {
            organization_id: activeOrganization.id,
            organization_name: activeOrganization.name,
          },
          canSwitch ? contextSwitchStatus : 403,
        );
      } else {
        const activeOrganization =
          organizations.find((item) => item.id === activeOrganizationId) ??
          organization;
        await json(route, {
          organization_id: activeOrganization.id,
          organization_name: activeOrganization.name,
        });
      }
      return;
    }
    if (url.pathname.endsWith("/organizations")) {
      await json(route, { items: organizations });
      return;
    }
    if (
      url.pathname === "/v1/animals" ||
      url.pathname === "/v1/animals/search"
    ) {
      await json(route, {
        items: [
          {
            id: "animal-a",
            name: "小森",
            shelter_number: "A-001",
            can_report: true,
            organization_id: "org-a",
          },
        ],
      });
      return;
    }
    if (url.pathname.match(/\/animals\/[^/]+\/confirm$/)) {
      await json(route, {
        id: "animal-a",
        name: "小森",
        shelter_number: "A-001",
        can_report: true,
        organization_id: "org-a",
        confirmation_token: "confirm-a",
      });
      return;
    }
    if (url.pathname === "/v1/care-report-drafts") {
      await json(route, { id: "draft-a" });
      return;
    }
    if (url.pathname.endsWith("/care-report/drafts/current")) {
      await json(route, {
        id: "draft-a",
        answers: {},
        current_step: "care",
        note: "",
      });
      return;
    }
    if (url.pathname.endsWith("/management/dashboard")) {
      await respond(
        route,
        options.dashboard ?? {
          organization_id: "org-a",
          role: "STAFF",
          summary: {
            reportable_animal_count: 4,
            today_report_count: 6,
            active_draft_count: 1,
            pending_ai_count: 2,
            alerts: [],
          },
          recent_reports: [],
        },
        options.dashboardStatus ?? 200,
      );
      return;
    }
    if (url.pathname.match(/\/organizations\/[^/]+\/areas$/)) {
      await json(route, { items: options.areas ?? [] });
      return;
    }
    if (url.pathname.match(/\/organizations\/[^/]+\/memberships$/)) {
      await json(route, {
        items: [
          {
            id: "membership-a",
            organization_id: "org-a",
            user_id: "user-a",
            role: "STAFF",
            status: "active",
          },
        ],
      });
      return;
    }
    if (url.pathname.endsWith("/management/ai-review")) {
      await json(route, {
        items: [
          {
            id: "observation-a",
            source_type: "note",
            source_id: "report-a",
            status: "succeeded",
            failure_reason: null,
            raw_ai_output: { observations: [{ code: "emotion.calm" }] },
            validated_ai_observation: {
              observations: [{ code: "emotion.calm" }],
            },
            human_review_result: null,
          },
        ],
      });
      return;
    }
    if (
      url.pathname === "/v1/observation-categories" ||
      url.pathname === "/v1/observation-options"
    ) {
      if (url.pathname.endsWith("observation-categories")) {
        await json(route, {
          items: [
            {
              id: "emotion",
              code: "emotion",
              display_name: "情緒",
              description: "動物情緒觀察",
              status: "active",
              display_order: 0,
              source: "platform_default",
            },
          ],
        });
      } else {
        await json(route, {
          items: [
            {
              id: "option-a",
              category_id: "emotion",
              organization_id: null,
              code: "emotion.calm",
              display_name: "平靜",
              description: "目前情緒穩定",
              status: "active",
              enabled: true,
              display_order: 0,
              requires_note: false,
              source: "platform_default",
              editable: false,
              has_historical_usage: false,
              historical_usage_count: 0,
              last_modified_at: "2026-08-14T00:00:00Z",
              last_modified_by: null,
              updated_at: "2026-08-14T00:00:00Z",
            },
          ],
          summary: {
            total: 1,
            active: 1,
            inactive: 0,
            custom: 0,
            scope: "admin_full",
          },
          category_counts: [
            {
              category_id: "emotion",
              active_count: 1,
              inactive_count: 0,
              custom_count: 0,
            },
          ],
        });
      }
      return;
    }
    if (url.pathname.endsWith("/management/audit")) {
      await json(route, {
        items: [
          {
            id: "audit-a",
            actor_user_id: "user-a",
            action: "observation_option.created",
            resource_type: "ObservationOption",
            resource_id: "option-a",
            reason: "P1 fixture",
            created_at: "2026-08-14T00:00:00Z",
          },
        ],
      });
      return;
    }
    if (url.pathname.endsWith("/management/qr-codes")) {
      await json(route, {
        items: [
          {
            id: "qr-a",
            animal_id: "animal-a",
            status: "active",
            revoked: false,
            deep_link: "https://example.test/animal/animal-a",
            token: null,
          },
        ],
      });
      return;
    }
    if (url.pathname.endsWith("/management/reportable-scopes")) {
      await json(route, {
        items: [
          {
            id: "scope-a",
            animal_id: "animal-a",
            area_id: null,
            volunteer_user_id: null,
            starts_at: "2026-08-14T00:00:00Z",
            ends_at: "2026-08-14T23:59:59Z",
            status: "active",
          },
        ],
      });
      return;
    }
    if (url.pathname === "/v1/management/care-agenda") {
      await json(route, {
        local_today: "2026-08-16",
        today_state: "no_activity",
        organization_timezone: "Asia/Taipei",
        timezone: "Asia/Taipei",
        timezone_version: 1,
        buckets: {
          today_pending: [],
          overdue: [],
          today_resolved: [],
          next_seven_days: [],
        },
        totals: {
          today_pending: 0,
          overdue: 0,
          today_resolved: 0,
          next_seven_days: 0,
        },
        pages: Object.fromEntries(
          ["today_pending", "overdue", "today_resolved", "next_seven_days"].map(
            (bucket) => [
              bucket,
              { items: [], total_count: 0, next_cursor: null },
            ],
          ),
        ),
      });
      return;
    }
    if (url.pathname.match(/\/v1\/assigned-care-reminders\/[^/]+$/)) {
      await json(route, {
        occurrence_id: "00000000-0000-4000-8000-000000000001",
        version: 0,
        status: "pending",
        animal: {
          id: "animal-a",
          name: "小森",
          shelter_number: "A-001",
          photo_url: null,
        },
        reminder_type: "medication",
        title: "今日照護指派",
        instructions: "依管理員指示執行。",
        display_local_at: "2026-08-16T09:00:00+08:00",
        can_complete: true,
        can_skip: true,
      });
      return;
    }
    if (url.pathname.match(/\/management\/animals\/[^/]+\/medical-records$/)) {
      await json(route, {
        items: [],
        total_count: 0,
        next_cursor: null,
      });
      return;
    }
    if (url.pathname.endsWith("/management/animals")) {
      const params = url.searchParams;
      const data = options.animals
        ? options.animals(params)
        : { items: [], page: 1, page_size: 20, total: 0 };
      await respond(
        route,
        data,
        options.animalsStatus ?? 200,
        options.animalDelay?.(params) ?? 0,
      );
      return;
    }
    if (url.pathname.endsWith("/management/reports")) {
      const params = url.searchParams;
      const data = options.reports
        ? options.reports(params)
        : { items: [], page: 1, page_size: 50, total: 0 };
      await respond(
        route,
        data,
        options.reportsStatus ?? 200,
        options.reportDelay?.(params) ?? 0,
      );
      return;
    }
    if (url.pathname.match(/\/management\/animals\/[^/]+$/)) {
      const animalId = url.pathname.split("/").pop() ?? "animal-a";
      await respond(
        route,
        {
          animal: options.animalDetails?.[animalId] ?? {
            id: "animal-a",
            name: "小森",
            shelter_number: "A-001",
            status: "active",
            photo_key: null,
            area_name: "一區",
            area_type: "room",
          },
        },
        options.animalDetailStatus ?? 200,
      );
      return;
    }
    if (url.pathname.match(/\/management\/reports\/[^/]+$/)) {
      const reportId = url.pathname.split("/").pop() ?? "report-a";
      await respond(
        route,
        {
          report: options.reportDetails?.[reportId] ?? {
            id: "report-a",
            animal_id: "animal-a",
            animal_name: "小森",
            status: "saved",
            submitted_at: "2026-08-14T00:00:00Z",
            answers: {},
            note: null,
            media_ids: [],
            ai_observations: [],
          },
        },
        options.reportDetailStatus ?? 200,
      );
      return;
    }
    if (url.pathname.match(/\/animals\/[^/]+\/timeline$/)) {
      const animalId = url.pathname.split("/").at(-2) ?? "animal-a";
      const params = url.searchParams;
      await respond(
        route,
        options.timelines?.(animalId, params) ?? { days: [] },
        options.timelineStatus ?? 200,
        options.timelineDelay?.(animalId, params) ?? 0,
      );
      return;
    }
    await json(route, {});
  });
}

export async function mockVolunteerApi(
  page: Page,
  options: { saveStatus?: number } = {},
) {
  let saveStatus = options.saveStatus ?? 200;
  const membershipValidFrom = new Date(Date.now() - 60_000).toISOString();
  const membershipExpiresAt = new Date(Date.now() + 3_600_000).toISOString();
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "test-access");
    sessionStorage.setItem("active_organization_id", "org-a");
    sessionStorage.setItem("active_organization_code", "ORG-A");
  });
  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/auth/me")) {
      await json(route, {
        user: {
          id: "volunteer-a",
          display_name: "志工甲",
          platform_role: null,
          status: "active",
        },
        memberships: [
          {
            id: "membership-a",
            organization_id: "org-a",
            role: "VOLUNTEER",
            status: "active",
            valid_from: membershipValidFrom,
            expires_at: membershipExpiresAt,
            access_grant: {
              membership_id: "membership-a",
              organization_id: "org-a",
              status: "active",
              valid_from: membershipValidFrom,
              expires_at: membershipExpiresAt,
            },
          },
        ],
      });
      return;
    }
    if (url.pathname.endsWith("/auth/active-shelter-context")) {
      await json(route, {
        organization_id: "org-a",
        organization_name: "浪浪森友會 A",
        session_id: "test-session",
      });
      return;
    }
    if (
      url.pathname === "/v1/animals" ||
      url.pathname === "/v1/animals/search"
    ) {
      await json(route, {
        items: [
          {
            id: "animal-a",
            name: "小森",
            shelter_number: "A-001",
            can_report: true,
            organization_id: "org-a",
          },
        ],
      });
      return;
    }
    if (url.pathname.match(/\/animals\/[^/]+\/confirm$/)) {
      await json(route, {
        id: "animal-a",
        name: "小森",
        shelter_number: "A-001",
        can_report: true,
        organization_id: "org-a",
        confirmation_token: "confirm-a",
      });
      return;
    }
    if (url.pathname === "/v1/care-report-drafts") {
      await json(route, { id: "draft-a" });
      return;
    }
    if (
      route.request().method() === "PATCH" &&
      url.pathname === "/v1/care-report-drafts/draft-a"
    ) {
      await json(
        route,
        {
          id: "draft-a",
          answers: {},
          current_step: "care",
          note: "",
        },
        saveStatus,
      );
      return;
    }
    if (url.pathname.endsWith("/care-report/drafts/current")) {
      await json(route, {
        id: "draft-a",
        answers: {},
        current_step: "care",
        note: "",
      });
      return;
    }
    await json(route, {});
  });
  return {
    setSaveStatus(nextStatus: number) {
      saveStatus = nextStatus;
    },
  };
}

type LoginFixtureOptions = {
  organizations?: (typeof organization)[];
  loginStatus?: FixtureStatus;
  contextSwitchStatus?: FixtureStatus;
};

export async function mockLoginApi(
  page: Page,
  input: (typeof organization)[] | LoginFixtureOptions = [organization],
) {
  const options = Array.isArray(input) ? {} : input;
  const organizations = Array.isArray(input)
    ? input
    : (input.organizations ?? [organization]);
  await page.route("**/v1/auth/me", async (route) => {
    if (route.request().method() !== "GET") {
      await json(route, { message: "Method Not Allowed" }, 405);
      return;
    }
    await json(route, {
      user: {
        id: "user-a",
        username: "local-staff-a",
        display_name: "林工作人員",
        platform_role: null,
        status: "active",
      },
      memberships: organizations.map((item, index) => ({
        id: `membership-${index + 1}`,
        organization_id: item.id,
        role: item.role,
        status: item.status,
      })),
    });
  });
  await page.route("**/v1/organizations", async (route) => {
    if (route.request().method() !== "GET") {
      await json(route, { message: "Method Not Allowed" }, 405);
      return;
    }
    await json(route, { items: organizations });
  });
  await page.route("**/v1/management/dashboard", async (route) => {
    if (route.request().method() !== "GET") {
      await json(route, { message: "Method Not Allowed" }, 405);
      return;
    }
    await json(route, {
      organization_id: organizations[0]?.id,
      role: organizations[0]?.role ?? "STAFF",
      summary: {
        reportable_animal_count: 0,
        today_report_count: 0,
        active_draft_count: 0,
        pending_ai_count: 0,
        alerts: [],
      },
      recent_reports: [],
    });
  });
  await page.route("**/v1/auth/login", async (route) => {
    await respond(
      route,
      {
        access_token: "test-access",
        refresh_token: "test-refresh",
        session_id: "test-session",
        organizations,
      },
      options.loginStatus ?? 200,
    );
  });
  await page.route("**/v1/auth/active-shelter-context", async (route) => {
    await respond(
      route,
      { organization_id: organizations[0]?.id },
      options.contextSwitchStatus ?? 200,
    );
  });
}
