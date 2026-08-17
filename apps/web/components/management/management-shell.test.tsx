import { describe, expect, it } from "vitest";
import React from "react";
import { AppSidebar } from "./AppSidebar";
import { ErrorState, EmptyState, LoadingState } from "./StateViews";
import { StatusBanner } from "./StatusBanner";
import { Breadcrumbs } from "./Breadcrumbs";
import { renderToStaticMarkup } from "react-dom/server";

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
});
