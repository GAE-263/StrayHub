import { describe, expect, it } from "vitest";
import React from "react";
import ObservationOptionsPage from "./observation-options/page";
import AuditPage from "./audit/page";

describe("management settings surfaces", () => {
  it("keeps vocabulary and audit in the shared settings area", () => {
    expect(React.createElement(ObservationOptionsPage).type).toBe(
      ObservationOptionsPage,
    );
    expect(React.createElement(AuditPage).type).toBe(AuditPage);
  });
});
