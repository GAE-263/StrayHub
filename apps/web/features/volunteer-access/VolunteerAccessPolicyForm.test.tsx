// @vitest-environment jsdom

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { VolunteerAccessPolicyForm } from "./VolunteerAccessPolicyForm";

describe("VolunteerAccessPolicyForm", () => {
  it("shows 168-hour initial policy and non-retroactive warning", () => {
    const html = renderToStaticMarkup(
      <VolunteerAccessPolicyForm
        policy={{
          organization_id: "org-a",
          applications_enabled: true,
          default_grant_duration_hours: 168,
          version: 1,
        }}
      />,
    );
    expect(html).toContain("168");
    expect(html).toContain("只影響後續建立的授權");
  });
});
