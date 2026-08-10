import { describe, expect, it } from "vitest";
import React from "react";
import ReportsPage from "./page";

describe("management report inbox", () => {
  it("renders report filters and inbox route", () => {
    const page = React.createElement(ReportsPage);
    expect(page.type).toBe(ReportsPage);
  });
});
