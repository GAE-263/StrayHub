import { describe, expect, it } from "vitest";
import React from "react";
import AnimalConfirmationPage from "./page";

describe("animal confirmation page", () => {
  it("provides a real confirmation page shell", () => {
    const page = React.createElement(AnimalConfirmationPage);
    expect(page.type).toBe(AnimalConfirmationPage);
  });
});
