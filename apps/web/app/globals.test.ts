import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("./globals.css", import.meta.url), "utf8");

function ruleBody(selector: string) {
  const match = css.match(
    new RegExp(
      `${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\{([^}]*)\\}`,
    ),
  );
  expect(match, `${selector} should be defined`).not.toBeNull();
  return match?.[1] ?? "";
}

describe("global animation contracts", () => {
  it("keeps skeleton opacity pulse separate from loading dot scaling", () => {
    expect(ruleBody(".ui-skeleton")).toContain("animation: skeleton-pulse");
    expect(ruleBody(".loading-dot")).toContain("animation: loading-dot-pulse");

    const skeletonPulse = ruleBody("@keyframes skeleton-pulse");
    const loadingDotPulse = ruleBody("@keyframes loading-dot-pulse");

    expect(skeletonPulse).toContain("opacity: 0.55");
    expect(skeletonPulse).not.toContain("transform:");
    expect(loadingDotPulse).toContain("opacity: 0.35");
    expect(loadingDotPulse).toContain("transform: scale(0.8)");
    expect(css).not.toMatch(/@keyframes\s+pulse\b/);
  });
});

describe("global dialog contracts", () => {
  it("centers permission confirmation dialogs in the viewport", () => {
    const permissionDialog = ruleBody(".permission-confirmation-dialog");

    expect(permissionDialog).toContain("inset: 0");
    expect(permissionDialog).toContain("margin: auto");
    expect(permissionDialog).toContain("position: fixed");
  });

  it("uses explicit surface tokens for dialogs and sheets", () => {
    const overlaySurface = ruleBody(".ui-dialog,\n.ui-sheet");

    expect(overlaySurface).toContain("background: var(--surface)");
    expect(overlaySurface).toContain("color: var(--foreground)");
  });

  it("keeps mobile sheet navigation readable as a vertical list", () => {
    const sheetNav = ruleBody(".ui-sheet nav");
    expect(sheetNav).toContain("display: grid");

    const sheetGroup = ruleBody(".ui-sheet .nav-group");
    expect(sheetGroup).toContain("display: grid");
    expect(sheetGroup).toContain("margin: 0");

    const sheetLink = ruleBody(".ui-sheet .nav-link");
    expect(sheetLink).toContain("min-height: 44px");
    expect(sheetLink).toContain("width: 100%");
  });

  it("anchors the navigation sheet to the full-height left edge", () => {
    const sheet = ruleBody("dialog.ui-sheet");

    expect(sheet).toContain(
      "border-radius: 0 var(--radius-lg) var(--radius-lg) 0",
    );
    expect(sheet).toContain("height: 100dvh");
    expect(sheet).toContain("inset: 0 auto 0 0");
    expect(sheet).toContain("margin: 0");
    expect(sheet).toContain("max-height: none");
    expect(sheet).toContain("position: fixed");
    expect(sheet).not.toContain("display: flex");
    expect(ruleBody("dialog.ui-sheet[open]")).toContain("display: flex");
  });
});

describe("global layout primitive contracts", () => {
  it("defines spacing, cluster, heading and list card layouts", () => {
    expect(ruleBody(".stack-sm")).toContain("gap: 12px");
    expect(ruleBody(".stack-md")).toContain("gap: 18px");
    expect(ruleBody(".stack-lg")).toContain("gap: 24px");

    const cluster = ruleBody(".cluster");
    expect(cluster).toContain("display: flex");
    expect(cluster).toContain("flex-wrap: wrap");

    const sectionHeading = ruleBody(".section-heading");
    expect(sectionHeading).toContain("justify-content: space-between");

    const listCard = ruleBody(".list-card");
    expect(listCard).toContain("background: var(--surface-soft)");
    expect(listCard).toContain("border: 1px solid var(--border)");

    expect(ruleBody(".toolbar.care-agenda-filters")).toContain(
      "align-items: flex-end",
    );
    expect(ruleBody(".care-agenda-filters .ui-field")).toContain(
      "margin-bottom: 0",
    );

    const reminderGrid = ruleBody(".reminder-card-grid");
    expect(reminderGrid).toContain("display: grid");
    expect(reminderGrid).toContain(
      "grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr))",
    );
  });
});

describe("mobile header contracts", () => {
  it("aligns an icon-only navigation trigger before the brand", () => {
    const brandGroup = ruleBody(".header-brand-group");
    expect(brandGroup).toContain("display: flex");
    expect(brandGroup).toContain("align-items: center");

    const trigger = ruleBody(".mobile-menu-trigger");
    expect(trigger).toContain("height: 44px");
    expect(trigger).toContain("width: 44px");
    expect(trigger).toContain("justify-content: center");

    expect(ruleBody(".app-header .header-logout")).toContain("display: none");

    const drawerLogout = ruleBody(".mobile-navigation-logout");
    expect(drawerLogout).toContain("justify-content: flex-start");
    expect(drawerLogout).toContain("width: 100%");
  });
});

describe("state view visual contracts", () => {
  it("colors fixed semantic icons from the state tone", () => {
    const icon = ruleBody(".state-icon");
    expect(icon).toContain("flex: 0 0 auto");
    expect(icon).toContain("margin-top: 2px");

    expect(ruleBody(".state-neutral .state-icon")).toContain(
      "color: var(--muted)",
    );
    expect(ruleBody(".state-danger .state-icon")).toContain(
      "color: var(--danger)",
    );
    expect(ruleBody(".state-warning .state-icon")).toContain(
      "color: var(--warning)",
    );
  });
});

describe("responsive app shell contracts", () => {
  it("uses one block per shell breakpoint and fills dynamic viewport height", () => {
    expect(css.match(/@media \(max-width: 900px\)/g)).toHaveLength(1);
    expect(css.match(/@media \(max-width: 600px\)/g)).toHaveLength(1);
    expect(css).not.toContain("calc(100vh - 72px)");

    const frame = ruleBody(".app-frame");
    expect(frame).toContain("display: flex");
    expect(frame).toContain("flex-direction: column");
    expect(frame).toContain("min-height: 100dvh");

    const body = ruleBody(".app-body");
    expect(body).toContain("flex: 1 1 auto");
    expect(body).toContain("min-height: 0");
  });
});
