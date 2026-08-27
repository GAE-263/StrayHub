import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AnimalConfirmationCard } from "./AnimalConfirmationCard";

describe("AnimalConfirmationCard", () => {
  it("shows safe profile guidance but never renders management behavior notes", () => {
    const animal = {
      id: "a",
      name: "獒瓦蛤",
      shelterName: "毛小孩幸福聯盟協會",
      canReport: true,
      sex: "female" as const,
      breed: "藏獒",
      age_description: "5歲以上",
      care_guidance: "飲食及零食請依現場安排。",
      behavior_notes: "內部管理描述",
    };
    const html = renderToStaticMarkup(
      <AnimalConfirmationCard
        animal={animal}
        onConfirm={() => undefined}
        onReselect={() => undefined}
      />,
    );
    expect(html).toContain("母 · 藏獒 · 5歲以上");
    expect(html).toContain("照護提醒");
    expect(html).toContain(animal.care_guidance);
    expect(html).not.toContain(animal.behavior_notes);
  });
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
