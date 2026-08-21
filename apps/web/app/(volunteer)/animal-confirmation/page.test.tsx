// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import AnimalConfirmationPage from "./page";
import { VolunteerShelterContext } from "../../../components/auth/VolunteerShelterContext";

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

  it("shows the server-confirmed shelter and clears animals when context changes", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
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
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [] }),
      } as Response);
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(
        <VolunteerShelterContext.Provider
          value={{ organizationId: "org-a", organizationName: "南港收容所" }}
        >
          <AnimalConfirmationPage />
        </VolunteerShelterContext.Provider>,
      );
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(container.textContent).toContain("目前協助收容所：南港收容所");
    expect(container.textContent).toContain("小森");

    await act(async () => {
      root?.render(
        <VolunteerShelterContext.Provider
          value={{ organizationId: "org-b", organizationName: "北投收容所" }}
        >
          <AnimalConfirmationPage />
        </VolunteerShelterContext.Provider>,
      );
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(container.textContent).toContain("目前協助收容所：北投收容所");
    expect(container.textContent).not.toContain("小森");
  });

  it("ignores a pending search response from the previous shelter", async () => {
    let resolveSearch!: (response: Response) => void;
    const pendingSearch = new Promise<Response>((resolve) => {
      resolveSearch = resolve;
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [] }),
      } as Response)
      .mockReturnValueOnce(pendingSearch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [] }),
      } as Response);
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(
        <VolunteerShelterContext.Provider
          value={{ organizationId: "org-a", organizationName: "南港收容所" }}
        >
          <AnimalConfirmationPage />
        </VolunteerShelterContext.Provider>,
      );
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    await act(async () => {
      const form = container?.querySelector(
        'form[aria-label="shelter-number-search-form"]',
      );
      form?.dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
      await Promise.resolve();
    });

    await act(async () => {
      root?.render(
        <VolunteerShelterContext.Provider
          value={{ organizationId: "org-b", organizationName: "北投收容所" }}
        >
          <AnimalConfirmationPage />
        </VolunteerShelterContext.Provider>,
      );
      await new Promise((resolve) => setTimeout(resolve, 0));
      resolveSearch({
        ok: true,
        json: async () => ({
          items: [
            {
              id: "old-animal",
              name: "舊收容所動物",
              shelter_number: "OLD-001",
              organization_id: "org-a",
              can_report: true,
            },
          ],
        }),
      } as Response);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(container?.textContent).not.toContain("舊收容所動物");
  });
});
