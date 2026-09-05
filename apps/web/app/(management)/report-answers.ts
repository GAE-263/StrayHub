/**
 * Turns stored observation codes into the wording staff actually recognise.
 *
 * A report stores `{category_code: option_code}`. Three sources can name those
 * codes, in descending order of trustworthiness:
 *   1. `answer_snapshots` — the wording captured when the volunteer submitted,
 *      so a later vocabulary edit cannot rewrite history.
 *   2. the current vocabulary — covers rows saved before snapshots existed.
 *   3. the code itself, made readable — never leaves a row blank.
 */

export type AnswerSnapshot = {
  code?: string | null;
  display_name?: string | null;
};

export type ObservationCategoryItem = {
  id: string;
  code: string;
  display_name: string;
};

export type ObservationOptionItem = {
  category_id: string;
  code: string;
  display_name: string;
  status?: string;
};

export type VocabularyOption = { code: string; label: string };

export type Vocabulary = {
  categoryLabels: Record<string, string>;
  optionLabels: Record<string, string>;
  optionsByCategory: Record<string, VocabularyOption[]>;
};

export const EMPTY_VOCABULARY: Vocabulary = {
  categoryLabels: {},
  optionLabels: {},
  optionsByCategory: {},
};

export function buildVocabulary(
  categories: ObservationCategoryItem[],
  options: ObservationOptionItem[],
): Vocabulary {
  const codeByCategoryId: Record<string, string> = {};
  const categoryLabels: Record<string, string> = {};
  for (const category of categories) {
    codeByCategoryId[category.id] = category.code;
    categoryLabels[category.code] = category.display_name;
  }
  const optionLabels: Record<string, string> = {};
  const optionsByCategory: Record<string, VocabularyOption[]> = {};
  for (const option of options) {
    if (option.status && option.status !== "active") continue;
    optionLabels[option.code] = option.display_name;
    const categoryCode = codeByCategoryId[option.category_id];
    if (!categoryCode) continue;
    (optionsByCategory[categoryCode] ??= []).push({
      code: option.code,
      label: option.display_name,
    });
  }
  return { categoryLabels, optionLabels, optionsByCategory };
}

/** `care_completion.completed` under `care_completion` reads as `Completed`. */
export function readableCode(code: string, categoryCode?: string): string {
  let text = code;
  if (categoryCode && text.startsWith(`${categoryCode}.`)) {
    text = text.slice(categoryCode.length + 1);
  }
  const lastDot = text.lastIndexOf(".");
  if (lastDot !== -1) text = text.slice(lastDot + 1);
  text = text.replace(/[_-]+/g, " ").trim();
  if (!text) return code;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export type DescribedAnswer = {
  /** The stored category code, used as the form field key. */
  key: string;
  categoryLabel: string;
  /** The stored option code, sent back unchanged unless staff edit it. */
  code: string;
  valueLabel: string;
  /**
   * False when no snapshot or vocabulary entry named this code, so the page can
   * keep showing the raw code instead of pretending it resolved one.
   */
  resolved: boolean;
};

export function describeAnswers(
  answers: Record<string, unknown> | null | undefined,
  snapshots: Record<string, AnswerSnapshot> | null | undefined,
  vocabulary: Vocabulary = EMPTY_VOCABULARY,
): DescribedAnswer[] {
  if (!answers) return [];
  return Object.entries(answers).map(([key, rawValue]) => {
    const code =
      typeof rawValue === "string" ? rawValue : String(rawValue ?? "");
    const snapshot = snapshots?.[key];
    const snapshotName =
      snapshot && (snapshot.code ?? code) === code
        ? (snapshot.display_name ?? "").trim()
        : "";
    const vocabularyName = vocabulary.optionLabels[code] ?? "";
    const resolvedName = snapshotName || vocabularyName;
    return {
      key,
      categoryLabel: vocabulary.categoryLabels[key] ?? readableCode(key),
      code,
      valueLabel: resolvedName || readableCode(code, key) || "未填寫",
      resolved: Boolean(resolvedName),
    };
  });
}

/**
 * Options offered for one answer. The stored code is always included, even when
 * the vocabulary no longer lists it, so opening the form cannot silently drop a
 * historical answer.
 */
export function correctionOptions(
  answer: DescribedAnswer,
  vocabulary: Vocabulary = EMPTY_VOCABULARY,
): VocabularyOption[] {
  const options = [...(vocabulary.optionsByCategory[answer.key] ?? [])];
  if (answer.code && !options.some((option) => option.code === answer.code)) {
    options.unshift({
      code: answer.code,
      label: `${answer.valueLabel}（現有值）`,
    });
  }
  return options;
}
