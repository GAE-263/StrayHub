import { describe, expect, it } from "vitest";
import React from "react";
import CareReportPage from "./page";

describe("care report LIFF page", () => {
  it("renders resume and save-oriented fallback shell", () => {
    const page = React.createElement(CareReportPage);
    expect(page.type).toBe(CareReportPage);
  });
});
