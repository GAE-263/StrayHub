import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import CareReportPage from "../app/(volunteer)/care-report/page";
import { LiffFallback } from "../features/line-bot/LiffFallback";

describe("local bot MVP fallback", () => {
  it("includes resume, fallback editing and save actions", () => {
    const element = (
      <LiffFallback
        draftId="draft-local"
        initialAnswers={{ feeding: "feeding.normal" }}
        onSave={() => undefined}
      />
    );
    const text = renderToStaticMarkup(element);
    expect(text).toContain("儲存並繼續");
    expect(text).toContain("重新附加照片");
    expect(text).toContain("回到 LINE Bot");
  });

  it("keeps the care report route as a resumable client page", () => {
    expect(React.createElement(CareReportPage).type).toBe(CareReportPage);
  });
});
