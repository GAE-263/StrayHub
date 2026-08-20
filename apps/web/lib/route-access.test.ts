import { describe, expect, it } from "vitest";

import { decideRouteAccess, routeAreaForPathname } from "./route-access";

describe("route access decision matrix", () => {
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
