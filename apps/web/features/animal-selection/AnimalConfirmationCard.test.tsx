import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AnimalConfirmationCard } from "./AnimalConfirmationCard";

describe("AnimalConfirmationCard", () => {
  it("uses a card-specific title id when the page title is present", () => {
    const html = renderToStaticMarkup(
      <>
        <h1 id="animal-confirmation-title">選擇照護動物</h1>
        <AnimalConfirmationCard
          animal={{ id: "animal-a", name: "小黑", canReport: true }}
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
    const element = AnimalConfirmationCard({
      animal: {
        id: "animal-a",
        name: "小黑",
        shelterNumber: "VAAAG114080610",
        photoUrl: "/animals/a.jpg",
        cage: "Cage 1",
        area: "北區",
        canReport: true,
      },
      onConfirm: () => undefined,
      onReselect: () => undefined,
    });
    const children = React.Children.toArray(element.props.children);
    const text = children
      .map((child) =>
        React.isValidElement<{ children?: React.ReactNode }>(child)
          ? child.props.children
          : child,
      )
      .join(" ");
    expect(text).toContain("VAAAG114080610");
    expect(text).toContain("Cage 1");
    expect(text).toContain("北區");
    expect(
      children.some(
        (child) => React.isValidElement(child) && child.type === "img",
      ),
    ).toBe(true);
  });

  it("disables confirmation when the candidate is not reportable", () => {
    const element = AnimalConfirmationCard({
      animal: { id: "animal-a", name: "小黑", canReport: false },
      onConfirm: () => undefined,
      onReselect: () => undefined,
    });
    const buttons = React.Children.toArray(element.props.children).filter(
      (child) => React.isValidElement(child) && child.type === "button",
    );
    expect(
      React.isValidElement<{ disabled?: boolean }>(buttons[0]) &&
        buttons[0].props.disabled,
    ).toBe(true);
  });
});
