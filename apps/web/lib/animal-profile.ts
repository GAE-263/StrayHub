import type { components } from "../../../packages/contracts/src/openapi";

export type ManagementAnimal = components["schemas"]["ManagementAnimal"];
export type AnimalProfileUpdate = components["schemas"]["AnimalProfileUpdate"];
export type SafeAnimalProfile = Partial<
  Pick<
    ManagementAnimal,
    | "sex"
    | "breed"
    | "birth_date"
    | "birth_date_estimated"
    | "age_description"
    | "care_guidance"
  >
>;

export function animalSexLabel(sex: SafeAnimalProfile["sex"]) {
  return sex === "male" ? "公" : sex === "female" ? "母" : "未知";
}

export function animalAgeLabel(
  profile: SafeAnimalProfile,
  today = new Date(),
): string {
  if (!profile.birth_date) return profile.age_description || "未知";
  const [year, month, day] = profile.birth_date.split("-").map(Number);
  let months = (today.getFullYear() - year) * 12 + today.getMonth() + 1 - month;
  if (today.getDate() < day) months -= 1;
  if (months < 0) return "未知";
  const age =
    months >= 12
      ? `${Math.floor(months / 12)}歲`
      : months > 0
        ? `${months}個月`
        : "未滿1個月";
  return profile.birth_date_estimated ? `約${age}` : age;
}

export function profileDateLabel(value: string | null | undefined) {
  return value ? value.replaceAll("-", "/") : "未提供";
}
