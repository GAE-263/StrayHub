import type { CurrentUser } from "./auth";
import type { EffectiveRole } from "./route-access";

export function canReviewVolunteerApplications(
  role: EffectiveRole | string | null | undefined,
): boolean {
  return role === "SHELTER_ADMIN" || role === "PLATFORM_ADMIN";
}

export function canManageCareQr(
  profile: CurrentUser,
  organizationId: string,
): boolean {
  if (!organizationId) return false;
  if (profile.user.platform_role === "PLATFORM_ADMIN") return true;
  return profile.memberships.some(
    (membership) =>
      membership.organization_id === organizationId &&
      membership.status === "active" &&
      membership.role === "SHELTER_ADMIN",
  );
}
