import type { EffectiveRole } from "./route-access";

export function canReviewVolunteerApplications(
  role: EffectiveRole | string | null | undefined,
): boolean {
  return role === "SHELTER_ADMIN" || role === "PLATFORM_ADMIN";
}
