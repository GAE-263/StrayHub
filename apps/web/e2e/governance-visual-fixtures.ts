import type { Page, Route } from "@playwright/test";

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

const memberships = [
  {
    id: "membership-admin",
    organization_id: "org-a",
    user_id: "platform-admin",
    username: "local-platform-admin",
    display_name: "本機平台管理員",
    role: "SHELTER_ADMIN",
    status: "active",
    access_version: 1,
    medical_care_access: false,
  },
  {
    id: "membership-staff",
    organization_id: "org-a",
    user_id: "staff-id",
    username: "local-staff-a",
    display_name: "本機工作人員 A",
    role: "STAFF",
    status: "disabled",
    access_version: 1,
    medical_care_access: false,
  },
  {
    id: "membership-volunteer",
    organization_id: "org-a",
    user_id: "volunteer-id",
    username: "local-volunteer-a",
    display_name: "本機志工 A",
    role: "VOLUNTEER",
    status: "disabled",
    access_version: 1,
    medical_care_access: false,
    volunteer_authorization_status: "revoked",
  },
];

export async function mockGovernanceVisualApi(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem("access_token", "platform-admin-test-token");
    sessionStorage.setItem("active_organization_id", "org-a");
  });
  await page.route("**/v1/**", async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname.endsWith("/auth/me")) {
      await json(route, {
        user: {
          id: "platform-admin",
          username: "local-platform-admin",
          display_name: "本機平台管理員",
          platform_role: "PLATFORM_ADMIN",
          status: "active",
        },
        memberships: [memberships[0]],
      });
      return;
    }
    if (pathname.endsWith("/auth/active-shelter-context")) {
      await json(route, { organization_id: "org-a" });
      return;
    }
    if (pathname === "/v1/organizations") {
      await json(route, {
        items: [
          {
            id: "org-a",
            code: "ORG-A",
            name: "浪浪森友會 A",
            status: "active",
            timezone: "Asia/Taipei",
            timezone_version: 1,
          },
        ],
      });
      return;
    }
    if (pathname.endsWith("/memberships/archived")) {
      await json(route, {
        items: [
          {
            id: "membership-archived",
            organization_id: "org-a",
            user_id: "archived-user",
            username: "archived-staff",
            display_name: "已封存工作人員",
            role: "STAFF",
            status: "archived",
            access_version: 1,
            archived_from_status: "disabled",
          },
        ],
      });
      return;
    }
    if (pathname.endsWith("/memberships")) {
      await json(route, { items: memberships });
      return;
    }
    if (pathname.endsWith("/areas")) {
      await json(route, {
        items: [
          {
            id: "area-a",
            name: "隔離區",
            area_type: "area",
            status: "active",
          },
          {
            id: "cage-a",
            name: "A-01",
            area_type: "cage",
            status: "inactive",
          },
        ],
      });
      return;
    }
    if (pathname.endsWith("/platform/administrators/candidates")) {
      await json(route, [
        {
          user_id: "candidate-a",
          username: "local-staff-a",
          display_name: "本機工作人員 A",
        },
      ]);
      return;
    }
    if (pathname.endsWith("/platform/administrators/audit")) {
      await json(route, []);
      return;
    }
    if (pathname === "/v1/platform/administrators") {
      await json(route, {
        policy: {
          min_active_admins: 1,
          max_active_admins: 2,
          active_count: 1,
          available_slots: 1,
        },
        items: [
          {
            user_id: "platform-admin",
            username: "local-platform-admin",
            display_name: "本機平台管理員",
            user_status: "active",
            platform_role: "PLATFORM_ADMIN",
            effective_status: "active",
            can_enable: false,
            can_disable: false,
            can_demote: false,
          },
        ],
      });
      return;
    }
    await json(route, {});
  });
}
