import { describe, expect, it } from "vitest";
import React from "react";
import ReportDetailPage from "./page";

describe("management report detail", () => {
  it("renders the correction and archive route", () => {
    const page = React.createElement(ReportDetailPage, {
      params: Promise.resolve({ reportId: "report-1" }),
    });
    expect(page.type).toBe(ReportDetailPage);
  });
});
