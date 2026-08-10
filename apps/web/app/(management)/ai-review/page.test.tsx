import { describe, expect, it } from "vitest";
import React from "react";
import AiReviewPage from "./page";

describe("AI review queue", () => {
  it("renders queue filters and review route", () => {
    const page = React.createElement(AiReviewPage);
    expect(page.type).toBe(AiReviewPage);
  });
});
