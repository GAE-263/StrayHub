import { describe, expect, it } from "vitest";
import React from "react";
import AnimalProfilePage from "./page";

describe("management animal profile", () => {
  it("renders the animal file route", () => {
    const page = React.createElement(AnimalProfilePage, {
      params: Promise.resolve({ animalId: "animal-1" }),
    });
    expect(page.type).toBe(AnimalProfilePage);
  });
});
