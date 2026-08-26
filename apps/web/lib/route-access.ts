export type EffectiveRole =
  "VOLUNTEER" | "STAFF" | "SHELTER_ADMIN" | "PLATFORM_ADMIN";

export type RouteArea = "public" | "volunteer" | "management";
export type AuthCheckState =
  | "checking"
  | "authenticated"
  | "unauthenticated"
  | "context-required"
  | "temporary-error"
  | "re-entry";
export type RouteDecisionState =
  | "allowed"
  | "checking"
  | "redirecting"
  | "context-required"
  | "temporary-error"
  | "re-entry";

export type RouteAccessInput = {
  pathname: string;
  authState: AuthCheckState;
  role?: string | null;
  hasActiveContext?: boolean;
};

export type RouteAccessDecision = {
  area: RouteArea;
  state: RouteDecisionState;
  destination?: "/login" | "/volunteer-entry" | "/animal-confirmation";
};

const MANAGEMENT_ROLES = new Set<EffectiveRole>([
  "STAFF",
  "SHELTER_ADMIN",
  "PLATFORM_ADMIN",
]);

function normalizePathname(pathname: string): string {
  const path = pathname.split(/[?#]/, 1)[0] || "/";
  if (path === "/") return path;
  return `/${path.replace(/^\/+|\/+$/g, "")}`;
}

export function routeAreaForPathname(pathname: string): RouteArea {
  const normalized = normalizePathname(pathname);
  if (normalized === "/volunteer-entry") return "public";
  if (
    normalized === "/animal-confirmation" ||
    normalized === "/care-report" ||
    normalized.startsWith("/assigned-care/")
  ) {
    return "volunteer";
  }
  return "management";
}

export function decideRouteAccess(
  input: RouteAccessInput,
): RouteAccessDecision {
  const area = routeAreaForPathname(input.pathname);
  if (area === "public") return { area, state: "allowed" };

  if (input.authState === "checking") return { area, state: "checking" };
  if (input.authState === "temporary-error") {
    return { area, state: "temporary-error" };
  }
  if (input.authState === "re-entry") return { area, state: "re-entry" };
  if (input.authState === "context-required") {
    return { area, state: "context-required" };
  }
  if (input.authState === "unauthenticated") {
    return {
      area,
      state: "redirecting",
      destination: area === "volunteer" ? "/volunteer-entry" : "/login",
    };
  }

  const role = input.role as EffectiveRole | undefined;
  if (!role || (!MANAGEMENT_ROLES.has(role) && role !== "VOLUNTEER")) {
    return { area, state: "context-required" };
  }
  if (!input.hasActiveContext) return { area, state: "context-required" };

  if (area === "volunteer") return { area, state: "allowed" };
  if (role === "VOLUNTEER") {
    return {
      area,
      state: "redirecting",
      destination: "/animal-confirmation",
    };
  }
  return { area, state: "allowed" };
}
