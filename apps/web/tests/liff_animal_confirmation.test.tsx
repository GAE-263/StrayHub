// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import AnimalConfirmationPage from "../app/(volunteer)/animal-confirmation/page";

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

const candidate: Candidate = {
  id: "animal-a",
  name: "小黑",
  shelter_number: "VAAAG114080610",
  photo_url: "/animals/a.jpg",
  cage: "Cage 1",
  area: "北區",
  organization_id: "org-a",
  can_report: true,
};

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

async function click(button: HTMLButtonElement) {
  await act(async () => {
    button.click();
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
  window.history.replaceState({}, "", "/");
  vi.unstubAllGlobals();
});

describe("LIFF animal confirmation", () => {
  it("loads a QR deep link, reports scan failure, then allows search fallback", async () => {
    window.history.replaceState(
      {},
      "",
      "/animal-confirmation?qr_token=qr-deep-link",
    );
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
      .mockResolvedValueOnce(
        jsonResponse({ message: "QR Code 無法辨識" }, false, 404),
      )
      .mockResolvedValueOnce(jsonResponse({ items: [candidate] }));

    await renderPage(fetchMock);
    const qrInput = container?.querySelector("#qr-token") as HTMLInputElement;
    expect(qrInput.value).toBe("qr-deep-link");

    await submit(
      container?.querySelector(
        'form[aria-label="qr-search-form"]',
      ) as HTMLFormElement,
    );
    expect(container?.querySelector('[role="alert"]')?.textContent).toContain(
      "QR Code 無法辨識",
    );

    const queryInput = container?.querySelector(
      "#shelter-number-query",
    ) as HTMLInputElement;
    await act(async () => {
      setInputValue(queryInput, "114080610");
    });
    await submit(
      container?.querySelector(
        'form[aria-label="shelter-number-search-form"]',
      ) as HTMLFormElement,
    );
    expect(container?.textContent).toContain("小黑／VAAAG114080610");
  });

  it("confirms a LIFF candidate and creates a draft within two explicit actions", async () => {
    window.history.replaceState({}, "", "/animal-confirmation");
    const confirmed = { ...candidate, confirmation_token: "confirmation-1" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ items: [candidate] }))
      .mockResolvedValueOnce(jsonResponse(confirmed))
      .mockResolvedValueOnce(jsonResponse({ id: "draft-1" }));

    await renderPage(fetchMock);
    const identifyButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.includes("查看確認卡"));
    expect(identifyButton).toBeInstanceOf(HTMLButtonElement);
    await click(identifyButton as HTMLButtonElement);
    expect(container?.textContent).toContain("請確認回報對象");

    const confirmButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.includes("確認是這隻"));
    expect(confirmButton).toBeInstanceOf(HTMLButtonElement);
    await click(confirmButton as HTMLButtonElement);

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[1][0])).toContain(
      "/v1/animals/animal-a/confirm",
    );
    const draftRequest = fetchMock.mock.calls[2][1] as RequestInit;
    expect(JSON.parse(String(draftRequest.body))).toEqual({
      animal_id: "animal-a",
      confirmation_token: "confirmation-1",
    });
    expect(container?.textContent).toContain("已建立回報草稿：draft-1");
  });
});
