import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import GrowthDiaryRoute from "./page";

vi.mock("../../../features/growth-diary/GrowthDiaryPage", () => ({
  GrowthDiaryPage: () => (
    <section data-testid="growth-diary-feature">日記功能</section>
  ),
}));

describe("growth diary management route", () => {
  it("only composes the feature page inside the existing management shell", () => {
    const html = renderToStaticMarkup(<GrowthDiaryRoute />);

    expect(html).toContain('data-testid="growth-diary-feature"');
    expect(html).not.toContain("<main");
  });

  it("keeps narrow layouts overflow-safe and gives controls visible focus", () => {
    const css = readFileSync(
      join(process.cwd(), "features/growth-diary/growth-diary.module.css"),
      "utf8",
    );

    expect(css).toMatch(/@media \(max-width: 640px\)/);
    expect(css).toMatch(/:focus-visible/);
    expect(css).toMatch(/overflow-x:\s*(clip|hidden)/);
  });
});
import { readFileSync } from "node:fs";
import { join } from "node:path";
