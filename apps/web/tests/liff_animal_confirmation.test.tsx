// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AnimalConfirmationPage from "../app/(volunteer)/animal-confirmation/page";
import { VolunteerShelterContext } from "../components/auth/VolunteerShelterContext";

const scanner = vi.hoisted(() => ({
  available: vi.fn(() => false),
  scan: vi.fn<() => Promise<string | null>>(),
}));

vi.mock("../lib/liff-scanner", () => ({
  isLiffScannerAvailable: scanner.available,
  scanAnimalQr: scanner.scan,
}));

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const candidate = {
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
  return { ok, status, json: async () => data } as Response;
}

async function flushEffects() {
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
}

let root: Root | undefined;
let container: HTMLDivElement | undefined;

async function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  window.sessionStorage.setItem("access_token", "active-session-token");
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
    await flushEffects();
  });
}

async function clickButton(label: string) {
  const button = Array.from(container?.querySelectorAll("button") ?? []).find(
    (item) => item.textContent?.includes(label),
  );
  expect(button).toBeInstanceOf(HTMLButtonElement);
  await act(async () => {
    (button as HTMLButtonElement).click();
    await flushEffects();
  });
}

beforeEach(() => {
  scanner.available.mockReset().mockReturnValue(false);
  scanner.scan.mockReset();
  window.history.replaceState({}, "", "/animal-confirmation");
  window.sessionStorage.clear();
});

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  container?.remove();
  container = undefined;
  vi.unstubAllGlobals();
});

describe("LIFF animal confirmation integration", () => {
  it("resolves a QR deep link with authenticated headers and hides the token from the URL", async () => {
    window.history.replaceState(
      {},
      "",
      "/animal-confirmation?organization_id=org-a&qr_token=qr-deep-link-token-123456",
    );
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(candidate));

    await renderPage(fetchMock);

    const requestHeaders = (fetchMock.mock.calls[0][1] as RequestInit)
      .headers as Headers;
    expect(requestHeaders.get("Authorization")).toBe(
      "Bearer active-session-token",
    );
    expect(String(fetchMock.mock.calls[0][0])).toBe("/v1/qr-tokens/resolve");
    expect(window.location.search).toBe("");
    expect(container?.textContent).toContain("VAAAG114080610");
    expect(container?.textContent).not.toContain("qr-deep-link-token-123456");
  });

  it("turns confirmed animal state into a pending handoff, never a draft", async () => {
    window.history.replaceState(
      {},
      "",
      "/animal-confirmation?organization_id=org-a&qr_token=qr-deep-link-token-123456",
    );
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(candidate))
      .mockResolvedValueOnce(
        jsonResponse({ ...candidate, confirmation_token: "confirmation-1" }),
      )
      .mockResolvedValueOnce(jsonResponse({ status: "pending" }));

    await renderPage(fetchMock);
    await clickButton("確認並開始回報");

    expect(String(fetchMock.mock.calls[1][0])).toContain(
      "/v1/animals/animal-a/confirm",
    );
    expect(String(fetchMock.mock.calls[2][0])).toBe("/v1/care-report-handoffs");
    expect(
      JSON.parse(String((fetchMock.mock.calls[2][1] as RequestInit).body)),
    ).toEqual({
      animal_id: "animal-a",
      confirmation_token: "confirmation-1",
      source: "qr_deeplink",
    });
    expect(fetchMock.mock.calls.flat().join(" ")).not.toContain(
      "/v1/care-report-drafts",
    );
    expect(container?.textContent).toContain("已準備好照護回報");
  });

  it("keeps fallback available when LIFF scanCodeV2 is unavailable", async () => {
    await renderPage(vi.fn());

    expect(container?.textContent).toContain("此裝置目前無法直接掃描 QR Code");
    await clickButton("輸入完整收容編號");
    expect(container?.querySelector("#exact-shelter-number")).toBeInstanceOf(
      HTMLInputElement,
    );
  });
});
