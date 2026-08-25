import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AnimalConfirmationCard } from "./AnimalConfirmationCard";

describe("AnimalConfirmationCard", () => {
  it("uses shared card structure with responsive media and actions hooks", () => {
    const html = renderToStaticMarkup(
      <AnimalConfirmationCard
        animal={{
          id: "animal-a",
          name: "小黑",
          shelterName: "南港收容所",
          canReport: true,
        }}
        onConfirm={() => undefined}
        onReselect={() => undefined}
      />,
    );

    expect(html).toContain('class="ui-card-header"');
    expect(html).toContain('class="ui-card-title"');
    expect(html).toContain(
      'class="ui-card-content animal-confirmation-content"',
    );
    expect(html).toContain('class="animal-confirmation-layout"');
    expect(html).toContain('class="animal-confirmation-actions"');
  });

  it("uses a card-specific title id when the page title is present", () => {
    const html = renderToStaticMarkup(
      <>
        <h1 id="animal-confirmation-title">選擇照護動物</h1>
        <AnimalConfirmationCard
          animal={{
            id: "animal-a",
            name: "小黑",
            shelterName: "南港收容所",
            canReport: true,
          }}
          onConfirm={() => undefined}
          onReselect={() => undefined}
        />
      </>,
    );

    const ids = Array.from(
      html.matchAll(/\sid="([^"]+)"/g),
      (match) => match[1],
    );
    expect(new Set(ids).size).toBe(ids.length);
    expect(html).toContain('aria-labelledby="animal-confirmation-card-title"');
    expect(html).toContain('id="animal-confirmation-card-title"');
  });

  it("renders every disambiguating identity field and explicit actions", () => {
    const html = renderToStaticMarkup(
      <AnimalConfirmationCard
        animal={{
          id: "animal-a",
          name: "小黑",
          shelterNumber: "VAAAG114080610",
          photoUrl: "/animals/a.jpg",
          cage: "Cage 1",
          area: "北區",
          shelterName: "南港收容所",
          canReport: true,
        }}
        onConfirm={() => undefined}
        onReselect={() => undefined}
      />,
    );
    expect(html).toContain("VAAAG114080610");
    expect(html).toContain("Cage 1");
    expect(html).toContain("北區");
    expect(html).toContain('<img src="/animals/a.jpg" alt="小黑 的照片"');
  });

  it("disables confirmation when the candidate is not reportable", () => {
    const html = renderToStaticMarkup(
      <AnimalConfirmationCard
        animal={{
          id: "animal-a",
          name: "小黑",
          shelterName: "南港收容所",
          canReport: false,
        }}
        onConfirm={() => undefined}
        onReselect={() => undefined}
      />,
    );
    expect(html).toMatch(
      /<button[^>]*disabled=""[^>]*>確認並開始回報<\/button>/,
    );
  });
});
