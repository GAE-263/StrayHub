import { describe, expect, it } from "vitest";
import { animalAgeLabel, animalSexLabel } from "./animal-profile";

describe("animal profile display", () => {
  const today = new Date(2026, 7, 26, 12);
  it("calculates exact age at the birthday without a stored integer", () => {
    expect(
      animalAgeLabel(
        { birth_date: "2021-08-26", age_description: "10歲以上" },
        today,
      ),
    ).toBe("5歲");
    expect(animalAgeLabel({ birth_date: "2021-08-27" }, today)).toBe("4歲");
  });
  it("labels estimated birth dates", () => {
    expect(
      animalAgeLabel(
        { birth_date: "2021-08-26", birth_date_estimated: true },
        today,
      ),
    ).toBe("約5歲");
  });
  it("keeps source-only age wording without inventing a birth date", () => {
    expect(animalAgeLabel({ age_description: "5歲以上" }, today)).toBe(
      "5歲以上",
    );
    expect(animalAgeLabel({}, today)).toBe("未知");
  });
  it("handles young animals and future dates safely", () => {
    expect(animalAgeLabel({ birth_date: "2026-07-26" }, today)).toBe("1個月");
    expect(animalAgeLabel({ birth_date: "2026-08-26" }, today)).toBe(
      "未滿1個月",
    );
    expect(animalAgeLabel({ birth_date: "2027-01-01" }, today)).toBe("未知");
  });
  it("uses Traditional Chinese sex labels", () => {
    expect(
      ["male", "female", "unknown"].map((sex) =>
        animalSexLabel(sex as "male" | "female" | "unknown"),
      ),
    ).toEqual(["公", "母", "未知"]);
  });
});
