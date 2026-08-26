// @vitest-environment jsdom

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import VolunteerRouteLayout from "./layout";

const navigation = vi.hoisted(() => ({ pathname: "/volunteer-entry" }));

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useRouter: () => ({ replace: vi.fn(), back: vi.fn() }),
}));

describe("volunteer route layout", () => {
  beforeEach(() => {
    navigation.pathname = "/volunteer-entry";
  });

  it("leaves the public LIFF entry outside the authenticated boundary", () => {
    const html = renderToStaticMarkup(
      <VolunteerRouteLayout>
        <p>public entry</p>
      </VolunteerRouteLayout>,
    );

    expect(html).toContain("public entry");
  });

  it("gates protected volunteer pages before mounting their children", () => {
    navigation.pathname = "/animal-confirmation";
    const html = renderToStaticMarkup(
      <VolunteerRouteLayout>
        <p>protected animal data</p>
      </VolunteerRouteLayout>,
    );

    expect(html).toContain("正在確認登入狀態");
    expect(html).not.toContain("protected animal data");
  });
});
