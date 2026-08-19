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
