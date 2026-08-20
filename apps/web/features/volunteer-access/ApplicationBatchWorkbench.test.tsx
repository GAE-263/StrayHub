// @vitest-environment jsdom

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ApplicationBatchWorkbench } from "./ApplicationBatchWorkbench";

describe("ApplicationBatchWorkbench", () => {
  it("keeps all-filtered snapshot count and partial results visible", () => {
    const html = renderToStaticMarkup(
      <ApplicationBatchWorkbench
        applications={Array.from({ length: 100 }, (_, index) => ({
          id: `app-${index}`,
          display_name: `志工 ${index}`,
          status: "pending",
          version: 1,
        }))}
        matchingCount={1200}
      />,
    );
    expect(html).toContain("目前篩選結果全部 1,200 筆");
    expect(html).toContain("共同授權期限");
    expect(html).toContain("逐筆結果");
    expect(html).toContain("ui-checkbox");
    expect(html).toContain("ui-input");
    expect(html).toContain("ui-table batch-table");
    expect(html).toContain("ui-button ui-button-default");
    expect(html).not.toContain("bg-emerald");
  });
});
