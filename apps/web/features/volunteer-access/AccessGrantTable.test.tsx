// @vitest-environment jsdom

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { AccessGrantTable } from "./AccessGrantTable";

describe("AccessGrantTable", () => {
  it("shows active mutation controls and immutable historical cycles", () => {
    const html = renderToStaticMarkup(
      <AccessGrantTable
        grants={[
          {
            id: "active",
            display_name: "志工 A",
            status: "active",
            valid_from: "2026-08-15T04:00:00Z",
            expires_at: "2026-08-22T04:00:00Z",
            version: 2,
            source_type: "manager_approval",
          },
          {
            id: "revoked",
            display_name: "志工 A",
            status: "revoked",
            valid_from: "2026-07-01T04:00:00Z",
            expires_at: "2026-07-08T04:00:00Z",
            version: 3,
            source_type: "manager_approval",
            revocation_reason: "排班異動",
          },
        ]}
        onMutate={vi.fn()}
      />,
    );
    expect(html).toContain("更新期限");
    expect(html).toContain("撤銷授權");
    expect(html).toContain('class="ui-field grant-status-filter"');
    expect(html).toContain('class="ui-input"');
    expect(html).toContain('class="ui-table grant-table"');
    expect(html).toContain("ui-button-secondary");
    expect(html).toContain("ui-button-destructive");
    expect(html).toContain("歷史週期（不可修改）");
    expect(html).toContain("排班異動");
  });
});
