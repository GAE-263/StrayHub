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
