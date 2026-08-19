// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import AnimalConfirmationPage from "./page";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | undefined;
let container: HTMLDivElement | undefined;

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  container?.remove();
  container = undefined;
  vi.unstubAllGlobals();
});

describe("animal confirmation page", () => {
  it("uses the volunteer shell and design-system controls for animal search", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Promise.resolve({
          ok: true,
          json: async () => ({
            items: [
              {
                id: "animal-a",
                name: "小森",
                shelter_number: "A-001",
                organization_id: "org-a",
                can_report: true,
              },
            ],
          }),
        } as Response),
      ),
    );
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<AnimalConfirmationPage />);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(container.querySelector("main.volunteer-page")).not.toBeNull();
    expect(
      container.querySelectorAll(".volunteer-search-card.ui-card"),
    ).toHaveLength(2);
    expect(container.querySelectorAll(".ui-field")).toHaveLength(2);
    expect(container.querySelectorAll("input.ui-input")).toHaveLength(2);
    expect(
      container.querySelectorAll("button.ui-button").length,
    ).toBeGreaterThanOrEqual(3);
    expect(container.querySelector(".volunteer-candidate-list")).not.toBeNull();
    expect(
      container.querySelector(".volunteer-candidate-item.list-card"),
    ).not.toBeNull();
    expect(container.querySelector("button.button")).toBeNull();
  });
});
