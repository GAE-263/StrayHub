import { describe, expect, it } from "vitest";
import {
  EMPTY_VOCABULARY,
  buildVocabulary,
  correctionOptions,
  describeAnswers,
  readableCode,
} from "./report-answers";

const categories = [
  { id: "cat-activity", code: "activity", display_name: "活動狀況" },
  { id: "cat-defecation", code: "defecation", display_name: "排便狀況" },
];
const options = [
  {
    category_id: "cat-activity",
    code: "activity.usual",
    display_name: "跟平常一樣",
    status: "active",
  },
  {
    category_id: "cat-activity",
    code: "activity.lower",
    display_name: "比平常差",
    status: "active",
  },
  {
    category_id: "cat-activity",
    code: "activity.retired",
    display_name: "已停用",
    status: "archived",
  },
];
const vocabulary = buildVocabulary(categories, options);

describe("observation vocabulary", () => {
  it("indexes categories and keeps only active options selectable", () => {
    expect(vocabulary.categoryLabels.activity).toBe("活動狀況");
    expect(vocabulary.optionsByCategory.activity).toEqual([
      { code: "activity.usual", label: "跟平常一樣" },
      { code: "activity.lower", label: "比平常差" },
    ]);
    expect(vocabulary.optionLabels["activity.retired"]).toBeUndefined();
  });
});

describe("describeAnswers", () => {
  it("prefers the wording captured when the report was submitted", () => {
    const [answer] = describeAnswers(
      { activity: "activity.usual" },
      { activity: { code: "activity.usual", display_name: "當天記錄的說法" } },
      vocabulary,
    );

    expect(answer.categoryLabel).toBe("活動狀況");
    expect(answer.valueLabel).toBe("當天記錄的說法");
    expect(answer.resolved).toBe(true);
  });

  it("falls back to the current vocabulary when no snapshot exists", () => {
    const [answer] = describeAnswers(
      { activity: "activity.lower" },
      null,
      vocabulary,
    );

    expect(answer.valueLabel).toBe("比平常差");
    expect(answer.resolved).toBe(true);
  });

  it("ignores a snapshot that names a different code than the stored answer", () => {
    const [answer] = describeAnswers(
      { activity: "activity.lower" },
      { activity: { code: "activity.usual", display_name: "跟平常一樣" } },
      vocabulary,
    );

    expect(answer.valueLabel).toBe("比平常差");
  });

  it("still reads sensibly for codes no vocabulary or snapshot covers", () => {
    const [answer] = describeAnswers(
      { care_completion: "care_completion.completed" },
      null,
      vocabulary,
    );

    expect(answer.categoryLabel).toBe("Care completion");
    expect(answer.valueLabel).toBe("Completed");
    // The page keeps showing the raw code when nothing named it.
    expect(answer.resolved).toBe(false);
    expect(answer.code).toBe("care_completion.completed");
  });

  it("returns no rows for an empty or missing answer set", () => {
    expect(describeAnswers({}, null, vocabulary)).toEqual([]);
    expect(describeAnswers(null, null, vocabulary)).toEqual([]);
  });
});

describe("correctionOptions", () => {
  it("offers the category's active options", () => {
    const [answer] = describeAnswers(
      { activity: "activity.usual" },
      null,
      vocabulary,
    );

    expect(
      correctionOptions(answer, vocabulary).map((item) => item.code),
    ).toEqual(["activity.usual", "activity.lower"]);
  });

  it("keeps a stored code the vocabulary dropped so a correction cannot lose it", () => {
    const [answer] = describeAnswers(
      { activity: "activity.retired" },
      { activity: { code: "activity.retired", display_name: "已停用" } },
      vocabulary,
    );
    const offered = correctionOptions(answer, vocabulary);

    expect(offered[0]).toEqual({
      code: "activity.retired",
      label: "已停用（現有值）",
    });
    expect(offered).toHaveLength(3);
  });

  it("degrades to just the stored value without a vocabulary", () => {
    const [answer] = describeAnswers({ activity: "activity.usual" }, null);

    expect(correctionOptions(answer, EMPTY_VOCABULARY)).toEqual([
      { code: "activity.usual", label: "Usual（現有值）" },
    ]);
  });
});

describe("readableCode", () => {
  it("drops the category prefix and separators", () => {
    expect(readableCode("appearance.skin_or_coat")).toBe("Skin or coat");
    expect(readableCode("walk_completion.not_done", "walk_completion")).toBe(
      "Not done",
    );
    expect(readableCode("emotion")).toBe("Emotion");
  });
});
