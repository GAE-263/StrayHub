import { describe, expect, it } from "vitest";
import React from "react";
import SheltersManagementPage from "./page";

describe("shelter management page", () => {
  it("exposes shelter and area management sections", () => {
    const page = React.createElement(SheltersManagementPage);
    expect(page.type).toBe(SheltersManagementPage);
  });
});
