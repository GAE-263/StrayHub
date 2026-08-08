import { describe, expect, it } from "vitest";
import React from "react";
import AnimalTimelinePage from "./page";

describe("animal timeline page", () => {
  it("renders the management timeline route", () => {
    const page = React.createElement(AnimalTimelinePage, {
      params: Promise.resolve({ animalId: "animal-1" }),
    });
    expect(page.type).toBe(AnimalTimelinePage);
  });
});
