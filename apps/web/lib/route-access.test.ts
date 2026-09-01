import { describe, expect, it } from "vitest";

import { decideRouteAccess, routeAreaForPathname } from "./route-access";
import {
  canManageCareQr,
  canReviewVolunteerApplications,
} from "./management-capabilities";
import type { CurrentUser } from "./auth";

describe("route access decision matrix", () => {
  it("limits volunteer review capability to admin roles", () => {
    expect(canReviewVolunteerApplications("STAFF")).toBe(false);
    expect(canReviewVolunteerApplications("SHELTER_ADMIN")).toBe(true);
    expect(canReviewVolunteerApplications("PLATFORM_ADMIN")).toBe(true);
  });

  it("scopes care QR mutation capability to the active shelter role", () => {
    const shelterAdmin = {
      user: { id: "user-a", platform_role: null, status: "active" },
      memberships: [
        {
          id: "membership-a",
          organization_id: "org-a",
          user_id: "user-a",
          role: "SHELTER_ADMIN",
          status: "active",
        },
      ],
    } satisfies CurrentUser;
    const staff = {
      ...shelterAdmin,
      memberships: [{ ...shelterAdmin.memberships[0], role: "STAFF" }],
    } satisfies CurrentUser;
    const platformAdmin = {
      user: {
        id: "platform-a",
        platform_role: "PLATFORM_ADMIN",
        status: "active",
      },
      memberships: [],
    } satisfies CurrentUser;

    expect(canManageCareQr(shelterAdmin, "org-a")).toBe(true);
    expect(canManageCareQr(shelterAdmin, "org-b")).toBe(false);
    expect(canManageCareQr(staff, "org-a")).toBe(false);
    expect(canManageCareQr(platformAdmin, "org-a")).toBe(true);
    expect(canManageCareQr(platformAdmin, "")).toBe(false);
  });

  it("keeps the public volunteer entry public regardless of session state", () => {
    expect(
      decideRouteAccess({
        pathname: "/volunteer-entry?entry=opaque",
        authState: "unauthenticated",
      }),
    ).toEqual({ area: "public", state: "allowed" });
  });

  it.each(["/", "/animals/animal-a?tab=timeline", "/reports/weekly/"])(
    "redirects a volunteer from %s to animal confirmation",
    (pathname) => {
      expect(
        decideRouteAccess({
          pathname,
          authState: "authenticated",
          role: "VOLUNTEER",
          hasActiveContext: true,
        }),
      ).toEqual({
        area: "management",
        state: "redirecting",
        destination: "/animal-confirmation",
      });
    },
  );

  it.each([
    "/settings/audit",
    "/ai-review",
    "/shelters",
    "/care-calendar",
    "/future-management-child",
  ])("redirects a volunteer from %s to animal confirmation", (pathname) => {
    expect(
      decideRouteAccess({
        pathname,
        authState: "authenticated",
        role: "VOLUNTEER",
        hasActiveContext: true,
      }),
    ).toEqual({
      area: "management",
      state: "redirecting",
      destination: "/animal-confirmation",
    });
  });

  it.each(["STAFF", "SHELTER_ADMIN", "PLATFORM_ADMIN"])(
    "allows %s on management routes only with server context",
    (role) => {
      expect(
        decideRouteAccess({
          pathname: "/settings/audit",
          authState: "authenticated",
          role,
          hasActiveContext: true,
        }),
      ).toEqual({ area: "management", state: "allowed" });
      expect(
        decideRouteAccess({
          pathname: "/settings/audit",
          authState: "authenticated",
          role,
          hasActiveContext: false,
        }),
      ).toEqual({ area: "management", state: "context-required" });
    },
  );

  it("allows a context-confirmed session on volunteer routes without role fallback", () => {
    expect(
      decideRouteAccess({
        pathname: "/animal-confirmation",
        authState: "authenticated",
        role: "VOLUNTEER",
        hasActiveContext: true,
      }),
    ).toEqual({ area: "volunteer", state: "allowed" });
  });

  it.each([
    ["checking", "checking"],
    ["temporary-error", "temporary-error"],
    ["re-entry", "re-entry"],
    ["context-required", "context-required"],
  ] as const)(
    "keeps %s finite state visible without mounting a route",
    (authState, state) => {
      expect(
        decideRouteAccess({
          pathname: "/animal-confirmation",
          authState,
        }),
      ).toEqual({ area: "volunteer", state });
    },
  );

  it("uses login for unauthenticated protected routes and entry for volunteer routes", () => {
    expect(
      decideRouteAccess({
        pathname: "/shelters",
        authState: "unauthenticated",
      }),
    ).toEqual({
      area: "management",
      state: "redirecting",
      destination: "/login",
    });
    expect(
      decideRouteAccess({
        pathname: "/care-report",
        authState: "unauthenticated",
      }),
    ).toEqual({
      area: "volunteer",
      state: "redirecting",
      destination: "/volunteer-entry",
    });
  });

  it("fails closed for unknown role and does not trust cached organization data", () => {
    expect(
      decideRouteAccess({
        pathname: "/",
        authState: "authenticated",
        role: "OWNER",
        hasActiveContext: true,
      }),
    ).toEqual({ area: "management", state: "context-required" });
  });

  it("classifies paths by pathname only, ignoring query, hash and trailing slash", () => {
    expect(routeAreaForPathname("/care-report/?entry=opaque#fragment")).toBe(
      "volunteer",
    );
    expect(routeAreaForPathname("/volunteer-entry?entry=opaque")).toBe(
      "public",
    );
    expect(routeAreaForPathname("/unknown-management-child/")).toBe(
      "management",
    );
  });
});
