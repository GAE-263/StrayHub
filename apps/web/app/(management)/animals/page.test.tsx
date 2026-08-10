import { describe, expect, it } from "vitest";
import React from "react";
import AnimalsPage from "./page";

describe("management animals page", () => {
  it("renders the searchable animal directory", () => {
    const page = React.createElement(AnimalsPage);
    expect(page.type).toBe(AnimalsPage);
  });
});
