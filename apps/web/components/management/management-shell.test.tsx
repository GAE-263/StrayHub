import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { AppHeader } from "./AppHeader";
import { AppSidebar } from "./AppSidebar";
import { Breadcrumbs } from "./Breadcrumbs";
import { MobileNavigation } from "./MobileNavigation";
import { ErrorState, EmptyState, LoadingState } from "./StateViews";
import { StatusBanner } from "./StatusBanner";

(globalThis as typeof globalThis & { React: typeof React }).React = React;

vi.mock("next/navigation", () => ({
  usePathname: () => "/animals",
}));

function collectManagementPages(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return collectManagementPages(path);
    return entry.name === "page.tsx" ? [path] : [];
  });
}

describe("management shell primitives", () => {
  it("exposes shared navigation and state components", () => {
    expect(React.createElement(AppSidebar, { role: "STAFF" }).type).toBe(
      AppSidebar,
    );
    expect(React.createElement(LoadingState, { title: "載入" }).type).toBe(
      LoadingState,
    );
    expect(React.createElement(EmptyState, { title: "空" }).type).toBe(
      EmptyState,
    );
    expect(React.createElement(ErrorState, { title: "錯誤" }).type).toBe(
      ErrorState,
    );
    expect(
      React.createElement(StatusBanner, { kind: "info", children: "狀態" })
        .type,
    ).toBe(StatusBanner);
  });

  it("keeps volunteer out of management navigation", () => {
    const sidebar = React.createElement(AppSidebar, { role: "VOLUNTEER" });
    expect(sidebar.props.role).toBe("VOLUNTEER");
  });

  it("keeps breadcrumb hierarchy labelled for assistive technology", () => {
    const html = renderToStaticMarkup(
      <Breadcrumbs
        items={[{ label: "動物檔案", href: "/animals" }, { label: "小森" }]}
      />,
    );
    expect(html).toContain('aria-label="Breadcrumb"');
    expect(html).toContain("動物檔案");
    expect(html).toContain("小森");
  });

  it("renders mobile navigation as an icon-only accessible trigger", () => {
    const html = renderToStaticMarkup(
      <MobileNavigation role="STAFF" onLogout={() => undefined} />,
    );

    expect(html).toContain('aria-label="開啟管理工作台導覽"');
    expect(html).not.toContain("<span>導覽</span>");
    expect(html).toContain("mobile-navigation-logout");
    expect(html).toContain('aria-label="登出管理工作台"');
    expect(html).toContain("lucide-log-out");
  });

  it("places the mobile navigation slot before the brand mark", () => {
    const html = renderToStaticMarkup(
      <AppHeader
        displayName="測試人員"
        organizationLabel="ORG-A"
        organizations={[]}
        activeOrganizationId="org-a"
        onSwitchOrganization={() => undefined}
        onLogout={() => undefined}
        mobileNavigation={<button data-mobile-navigation="true" />}
      />,
    );

    expect(html.indexOf('data-mobile-navigation="true"')).toBeGreaterThan(-1);
    expect(html.indexOf('data-mobile-navigation="true"')).toBeLessThan(
      html.indexOf('class="brand-mark"'),
    );
    expect(html).toContain("header-logout");
  });

  it("delegates the single main landmark to ManagementLayout", () => {
    const pages = [
      ...collectManagementPages(join(process.cwd(), "app/(management)")),
      join(
        process.cwd(),
        "features/observation-vocabulary/ObservationVocabularyPage.tsx",
      ),
    ];
    const layout = readFileSync(
      join(process.cwd(), "components/management/ManagementLayout.tsx"),
      "utf8",
    );

    expect(pages.length).toBeGreaterThan(0);
    for (const page of pages) {
      expect(readFileSync(page, "utf8"), page).not.toMatch(/<main(?:\s|>)/);
    }
    expect(layout.match(/<main(?:\s|>)/g)).toHaveLength(1);
  });
});
