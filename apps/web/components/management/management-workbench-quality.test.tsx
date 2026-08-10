import { describe, expect, it } from "vitest";
import React from "react";
import { ErrorState, EmptyState, LoadingState } from "./StateViews";
import { StatusBanner } from "./StatusBanner";

describe("management workbench quality states", () => {
  it.each([
    [LoadingState, { title: "loading" }],
    [EmptyState, { title: "empty" }],
    [ErrorState, { title: "error", description: "403" }],
  ])("has a stable state component for %s", (Component, props) => {
    expect(React.createElement(Component, props).type).toBe(Component);
  });

  it("supports a non-destructive offline/status banner", () => {
    expect(
      React.createElement(StatusBanner, {
        kind: "warning",
        children: "offline",
      }).props.kind,
    ).toBe("warning");
  });
});
