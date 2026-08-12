import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import ObservationVocabularyPage from "./ObservationVocabularyPage";

describe("ObservationVocabularyPage", () => {
  it("starts with a readable title and non-zero-loading state", () => {
    const html = renderToStaticMarkup(
      React.createElement(ObservationVocabularyPage),
    );

    expect(html).toContain("觀察詞彙");
    expect(html).toContain("標準化觀察語彙管理");
    expect(html).toContain("正在載入觀察詞彙");
    expect(html).toContain('role="status"');
    expect(html).not.toContain("觀察類別數量：0");
  });
});
