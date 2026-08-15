// @vitest-environment jsdom

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { VolunteerApplicationPage } from "./VolunteerApplicationPage";

describe("VolunteerApplicationPage", () => {
  it.each([
    ["none", "立即報名"],
    ["pending", "等待收容所審核"],
    ["rejected", "再次報名"],
    ["withdrawn", "再次報名"],
    ["expired", "授權已到期"],
  ])(
    "renders Traditional Chinese state %s without protected content",
    (status, copy) => {
      const html = renderToStaticMarkup(
        <VolunteerApplicationPage
          initialStatus={{
            organization: {
              id: "org-a",
              name: "收容所 A",
              applications_enabled: true,
            },
            application:
              status === "none" ? null : { id: "app-a", status, version: 1 },
            grant: null,
            effective_status: status,
            next_actions:
              status === "pending" ? ["wait", "withdraw"] : ["reapply"],
          }}
          idToken="id-token"
          shelterEntryReference="entry"
        />,
      );
      expect(html).toContain(copy);
      expect(html).not.toContain("狗狗名單");
      expect(html).not.toContain("管理後台");
    },
  );

  it("shows upcoming/active grant period in Taiwan time and only active handoff", () => {
    const status = {
      organization: {
        id: "org-a",
        name: "收容所 A",
        applications_enabled: true,
      },
      application: { id: "app-a", status: "approved", version: 2 },
      grant: {
        id: "grant-a",
        status: "active",
        valid_from: "2026-08-15T04:00:00Z",
        expires_at: "2026-08-22T04:00:00Z",
        version: 1,
      },
      effective_status: "active",
      next_actions: ["enter_care"],
    };
    const active = renderToStaticMarkup(
      <VolunteerApplicationPage
        initialStatus={status}
        idToken="id-token"
        shelterEntryReference="entry"
      />,
    );
    expect(active).toContain("收容所 A");
    expect(active).toContain("2026/08/15");
    expect(active).toContain("12:00");
    expect(active).toContain("進入照護流程");

    const upcoming = renderToStaticMarkup(
      <VolunteerApplicationPage
        initialStatus={{ ...status, effective_status: "upcoming" }}
        idToken="id-token"
        shelterEntryReference="entry"
      />,
    );
    expect(upcoming).not.toContain("進入照護流程</a>");
  });
});
