import { describe, expect, it } from "vitest";
import React from "react";
import { LiffFallback } from "../../apps/web/features/line-bot/LiffFallback";

describe("LIFF fallback", () => {
  it("exposes long note, resume, batch edit, media retry and bot fallback actions", () => {
    const element = LiffFallback({
      initialAnswers: { feeding: "feeding.normal" },
      draftId: "draft-1",
      onSave: () => undefined,
    });
    const text = JSON.stringify(element);
    expect(text).toContain("繼續");
    expect(text).toContain("重新附加照片");
    expect(text).toContain("回到 LINE Bot");
  });
});
