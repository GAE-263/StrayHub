import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ObservationOptionsPage from "../../apps/web/app/(management)/settings/observation-options/page";


describe("observation vocabulary management page", () => {
  it("shows source, stable code, creation and history-management affordances", () => {
    const html = renderToStaticMarkup(React.createElement(ObservationOptionsPage));
    expect(html).toContain("標準化觀察語彙管理");
    expect(html).toContain("平台預設");
    expect(html).toContain("穩定 Code");
    expect(html).toContain("建立選項");
    expect(html).toContain("停用");
    expect(html).toContain("歷史回報仍保留原始顯示快照");
  });

  it("renders a permission error region for failed management requests", () => {
    const html = renderToStaticMarkup(React.createElement(ObservationOptionsPage));
    expect(html).toContain('role="alert"');
    expect(html).toContain('role="status"');
  });
});
