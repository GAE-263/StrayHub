import type { Page, Route } from "@playwright/test";

type VolunteerAccessOrganization = {
  id: string;
  code: string;
  name: string;
};

type VolunteerAccessFixtureOptions = {
  organizations?: VolunteerAccessOrganization[];
  activeOrganizationId?: string;
  memberships?: Array<{
    id: string;
    organization_id: string;
    role: string;
    status: string;
  }>;
};

export async function mockLiffBrowser(
  page: Page,
  liffId = "fake-liff-id",
  idToken = "local-id-token",
) {
  await page.addInitScript(
    ({ configuredLiffId, configuredIdToken }) => {
      localStorage.setItem(
        `LIFF_STORE:${configuredLiffId}:accessToken`,
        JSON.stringify("local-liff-access-token"),
      );
      localStorage.setItem(
        `LIFF_STORE:${configuredLiffId}:IDToken`,
        JSON.stringify(configuredIdToken),
      );
      localStorage.setItem(
        `LIFF_STORE:${configuredLiffId}:expires`,
        JSON.stringify(Date.now() + 60 * 60 * 1000),
      );
      document.cookie = `LIFF_STORE:expires:${configuredLiffId}=${Date.now() + 60 * 60 * 1000}; path=/`;
    },
    { configuredLiffId: liffId, configuredIdToken: idToken },
  );
  await page.route(
    "https://api.line.me/liff/v2/apps/**/contextToken",
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ token: "local-context-token" }),
      });
    },
  );
}

export async function mockVolunteerAccessApi(
  page: Page,
  options: VolunteerAccessFixtureOptions = {},
) {
  const organizations = options.organizations ?? [
    { id: "org-a", code: "ORG-A", name: "收容所 A" },
  ];
  let activeOrganizationId =
    options.activeOrganizationId ?? organizations[0]?.id ?? "org-a";
  const memberships =
    options.memberships ??
    organizations.map((item) => ({
      id: `membership-${item.id}`,
      organization_id: item.id,
      role: "SHELTER_ADMIN",
      status: "active",
    }));
  await page.addInitScript((organizationId) => {
    sessionStorage.setItem("access_token", "test-access");
    if (!sessionStorage.getItem("active_organization_id")) {
      sessionStorage.setItem("active_organization_id", organizationId);
      sessionStorage.setItem(
        "active_organization_code",
        organizationId.toUpperCase(),
      );
    }
  }, activeOrganizationId);
  await page.route("**/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    let responseStatus = 200;
    if (path.endsWith("/auth/me")) {
      body = {
        user: { id: "admin-a", display_name: "管理員", status: "active" },
        memberships,
      };
    } else if (path.endsWith("/auth/active-shelter-context")) {
      if (route.request().method() === "PUT") {
        const payload = route.request().postDataJSON() as {
          organization_id?: string;
        };
        const requestedOrganizationId = payload.organization_id;
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
        } else {
          responseStatus = 403;
        }
      }
      const activeOrganization =
        organizations.find((item) => item.id === activeOrganizationId) ??
        organizations[0];
      body = {
        organization_id: activeOrganization?.id ?? "org-a",
        organization_name: activeOrganization?.name ?? "收容所 A",
      };
    } else if (path === "/v1/organizations") {
      body = { items: organizations };
    } else if (path.endsWith("/volunteer-applications/status")) {
      body = {
        organization: {
          id: "org-a",
          name: "收容所 A",
          applications_enabled: true,
        },
        application: null,
        grant: null,
        effective_status: "none",
        next_actions: ["apply"],
      };
    } else if (path.endsWith("/volunteer-applications")) {
      body = {
        items: Array.from({ length: 100 }, (_, index) => ({
          id: `app-${index}`,
          display_name:
            index === 0
              ? "王小明（名字很長的鍵盤與窄螢幕驗證志工）"
              : `志工 ${index + 1}`,
          status: "pending",
          version: 1,
        })),
        matching_count: 1200,
        next_cursor: null,
      };
    } else if (path.endsWith("/volunteer-decision-batches")) {
      body = {
        id: "batch-a",
        requested_count: 1200,
        processed_count: 1200,
        succeeded_count: 1198,
        conflict_count: 1,
        failed_count: 1,
        status: "completed_with_errors",
      };
    } else if (path.endsWith("/items")) {
      body = {
        items: [
          {
            id: "item-success",
            application_id: "app-0",
            expected_version: 1,
            result: "succeeded",
          },
          {
            id: "item-conflict",
            application_id: "app-1",
            expected_version: 1,
            result: "conflict",
            error_code: "stale_version",
          },
          {
            id: "item-failed",
            application_id: "app-2",
            expected_version: 1,
            result: "failed",
            error_code: "temporary_failure",
          },
        ],
        next_cursor: null,
      };
    } else if (path.endsWith("/volunteer-access-policy")) {
      body = {
        organization_id: "org-a",
        applications_enabled: true,
        default_grant_duration_hours: 168,
        version: 1,
      };
    } else if (path.endsWith("/volunteer-access-grants")) {
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
    } else if (path.endsWith("/volunteer-notifications")) {
      body = {
        items: [
          {
            id: "notification-failed",
            recipient_display_name: "志工 A",
            event_type: "grant_approved",
            status: "failed",
            attempt_count: 3,
            last_error_code: "line_unavailable",
            last_failed_at: "2026-08-15T04:00:00Z",
          },
          {
            id: "notification-wait",
            recipient_display_name: "志工 B",
            event_type: "grant_expired",
            status: "retry_wait",
            attempt_count: 1,
            last_error_code: "rate_limited",
            last_failed_at: "2026-08-15T04:05:00Z",
          },
        ],
        next_cursor: null,
      };
    } else if (path.endsWith("/volunteer-notifications/retry")) {
      body = { requeued_count: 1, conflict_count: 0 };
    }
    await route.fulfill({
      status: responseStatus,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}
