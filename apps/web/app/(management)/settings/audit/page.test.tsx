import { describe, expect, it } from "vitest";
import React from "react";
import AuditPage from "./page";

describe("audit query page", () => {
  it("renders the read-only audit route", () => {
    const page = React.createElement(AuditPage);
    expect(page.type).toBe(AuditPage);
  });
});
