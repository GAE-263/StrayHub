// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import AnimalConfirmationPage from "../app/(volunteer)/animal-confirmation/page";
import { AnimalConfirmationCard } from "../features/animal-selection/AnimalConfirmationCard";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

type Candidate = {
  id: string;
  name: string;
  shelter_number: string;
  photo_url: string;
  cage: string;
  area: string;
  organization_id: string;
  can_report: boolean;
};

const candidates: Candidate[] = [
  {
    id: "animal-a",
    name: "小黑",
    shelter_number: "VAAAG114080610",
    photo_url: "/animals/a.jpg",
    cage: "Cage 1",
    area: "北區",
    organization_id: "org-a",
    can_report: true,
  },
  {
    id: "animal-b",
    name: "小黑",
    shelter_number: "VAAAG114080611",
    photo_url: "/animals/b.jpg",
    cage: "Cage 2",
    area: "北區",
    organization_id: "org-a",
    can_report: true,
  },
];

function jsonResponse(data: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => data,
  } as Response;
}

async function flushEffects() {
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
}

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value",
  )?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

let root: Root | undefined;
let container: HTMLDivElement | undefined;

async function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(<AnimalConfirmationPage />);
    await flushEffects();
  });
}

async function submit(form: HTMLFormElement) {
  await act(async () => {
    form.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
    await flushEffects();
  });
}

afterEach(async () => {
  await act(async () => {
    root?.unmount();
  });
  root = undefined;
  container?.remove();
  container = undefined;
  vi.unstubAllGlobals();
});

describe("animal disambiguation", () => {
  it("keeps same-name search results separate with full shelter identity", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
      .mockResolvedValueOnce(jsonResponse({ items: candidates }));

    await renderPage(fetchMock);
    const queryInput = container?.querySelector(
      "#shelter-number-query",
    ) as HTMLInputElement;
    await act(async () => {
      setInputValue(queryInput, "11408061");
    });
    await submit(
      container?.querySelector(
        'form[aria-label="shelter-number-search-form"]',
      ) as HTMLFormElement,
    );

    const results = container?.querySelectorAll(
      'section[aria-labelledby="today-list-title"] li',
    );
    expect(results).toHaveLength(2);
    expect(container?.textContent).toContain("小黑／VAAAG114080610");
    expect(container?.textContent).toContain("小黑／VAAAG114080611");
  });

  it("shows photo, name, full shelter number and cage for similar candidates", () => {
    const html = candidates
      .map((candidate) =>
        React.createElement(AnimalConfirmationCard, {
          animal: {
            id: candidate.id,
            name: candidate.name,
            shelterNumber: candidate.shelter_number,
            photoUrl: candidate.photo_url,
            cage: candidate.cage,
            area: candidate.area,
            canReport: candidate.can_report,
          },
          onConfirm: () => undefined,
          onReselect: () => undefined,
        }),
      )
      .map((element) => renderToStaticMarkup(element));

    expect(html).toHaveLength(2);
    expect(html.join(" ")).toContain("/animals/a.jpg");
    expect(html.join(" ")).toContain("/animals/b.jpg");
    expect(html.join(" ")).toContain("VAAAG114080610");
    expect(html.join(" ")).toContain("VAAAG114080611");
    expect(html.join(" ")).toContain("Cage 1");
    expect(html.join(" ")).toContain("Cage 2");
  });
});
