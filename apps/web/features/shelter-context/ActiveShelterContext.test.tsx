import React from "react";
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ActiveShelterContext } from "./ActiveShelterContext";

describe("ActiveShelterContext", () => {
  it("requires an explicit switch action", () => {
    const onSwitch = vi.fn();
    const view = ActiveShelterContext({
      organizationName: "南港收容所",
      onSwitch,
    });
    expect(view.props["aria-label"]).toBe("目前收容所");
    expect(view.props.children[0].props.children).toContain("南港收容所");
    view.props.children[2].props.onClick();
    expect(onSwitch).toHaveBeenCalledOnce();
  });

  it("uses semantic context, warning, and action primitives", () => {
    const html = renderToStaticMarkup(
      <ActiveShelterContext
        organizationName="南港收容所"
        contextMismatch
        onSwitch={vi.fn()}
      />,
    );
    expect(html).toContain("active-shelter-context");
    expect(html).toContain("ui-badge");
    expect(html).toContain('role="alert"');
    expect(html).toContain("ui-button-secondary");
  });
});
