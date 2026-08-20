import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import CareReportPage from "./page";

describe("care report LIFF page", () => {
  it("renders resume and save-oriented fallback shell", () => {
    const page = React.createElement(CareReportPage);
    expect(page.type).toBe(CareReportPage);
    const html = renderToStaticMarkup(<CareReportPage />);
    expect(html).toContain("正在恢復回報草稿");
    expect(html).toContain("state-card");
    expect(html).toContain('role="status"');
  });
});
