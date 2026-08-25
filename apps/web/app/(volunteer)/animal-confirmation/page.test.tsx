// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { VolunteerShelterContext } from "../../../components/auth/VolunteerShelterContext";
import AnimalConfirmationPage from "./page";

const scanner = vi.hoisted(() => ({
  available: vi.fn(() => false),
  scan: vi.fn<() => Promise<string | null>>(),
}));

vi.mock("../../../lib/liff-scanner", () => ({
  isLiffScannerAvailable: scanner.available,
  scanAnimalQr: scanner.scan,
}));

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const candidate = {
  id: "animal-a",
  name: "小黑",
  shelter_number: "A-013",
  photo_url: "/animals/a.jpg",
  cage: "A3",
  area: "犬舍",
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

async function renderPage(
  fetchMock: ReturnType<typeof vi.fn>,
  context = { organizationId: "org-a", organizationName: "南港收容所" },
) {
  vi.stubGlobal("fetch", fetchMock);
  window.sessionStorage.setItem("access_token", "active-session-token");
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(
      <VolunteerShelterContext.Provider value={context}>
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
  HTMLDialogElement.prototype.showModal = vi.fn(function showModal(
    this: HTMLDialogElement,
  ) {
    this.setAttribute("open", "");
  });
  HTMLDialogElement.prototype.close = vi.fn(function close(
    this: HTMLDialogElement,
  ) {
    this.removeAttribute("open");
  });
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

describe("QR-first animal confirmation page", () => {
  it("starts scanner-first and keeps exact-number fallback usable when scanning is unavailable", async () => {
    await renderPage(vi.fn());

    expect(container?.textContent).toContain("掃描動物上的 QR Code");
    expect(container?.textContent).toContain("掃描動物 QR Code");
    expect(container?.textContent).toContain("輸入完整收容編號");
    expect(container?.textContent).toContain("此裝置目前無法直接掃描 QR Code");
    expect(container?.textContent).not.toContain("QR Token");
    expect(container?.querySelector("#qr-token")).toBeNull();
    expect(container?.textContent).not.toContain("今日可回報動物");

    await clickButton("輸入完整收容編號");
    expect(container?.querySelector("#exact-shelter-number")).toBeInstanceOf(
      HTMLInputElement,
    );
  });

  it("resolves a same-shelter deep link directly into the confirmation card", async () => {
    window.history.replaceState(
      {},
      "",
      "/animal-confirmation?organization_id=org-a&qr_token=direct-token-123456789",
    );
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(candidate));

    await renderPage(fetchMock);

    expect(String(fetchMock.mock.calls[0][0])).toBe("/v1/qr-tokens/resolve");
    expect(container?.textContent).toContain("確認照護動物");
    expect(container?.textContent).toContain("小黑");
    expect(container?.textContent).toContain("南港收容所");
    expect(container?.querySelector('[role="dialog"]')).toBeNull();
    expect(window.location.search).toBe("");
  });

  it("authorizes a foreign shelter before showing an explicit switch dialog and cancel preserves A", async () => {
    window.history.replaceState(
      {},
      "",
      "/animal-confirmation?organization_id=org-b&qr_token=foreign-token-123456789",
    );
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        organization_id: "org-b",
        organization_name: "北投收容所",
      }),
    );

    await renderPage(fetchMock);

    expect(String(fetchMock.mock.calls[0][0])).toBe(
      "/v1/qr-tokens/candidate-organization",
    );
    expect(container?.querySelector('[role="dialog"]')).not.toBeNull();
    expect(container?.textContent).toContain("你目前正在協助「南港收容所」");
    expect(container?.textContent).not.toContain("小黑");

    await clickButton("取消");
    expect(container?.querySelector('[role="dialog"]')).toBeNull();
    expect(container?.textContent).toContain("目前協助收容所：南港收容所");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("switches only after confirmation, then resolves and shows the B animal", async () => {
    window.history.replaceState(
      {},
      "",
      "/animal-confirmation?organization_id=org-b&qr_token=foreign-token-123456789",
    );
    const candidateB = {
      ...candidate,
      id: "animal-b",
      name: "小白",
      organization_id: "org-b",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          organization_id: "org-b",
          organization_name: "北投收容所",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          organization_id: "org-b",
          organization_name: "北投收容所",
        }),
      )
      .mockResolvedValueOnce(jsonResponse(candidateB));

    await renderPage(fetchMock);
    await clickButton("切換並繼續");

    expect(String(fetchMock.mock.calls[1][0])).toBe(
      "/v1/auth/active-shelter-context",
    );
    expect((fetchMock.mock.calls[1][1] as RequestInit).method).toBe("PUT");
    expect(String(fetchMock.mock.calls[2][0])).toBe("/v1/qr-tokens/resolve");
    expect(container?.textContent).toContain("小白");
    expect(container?.textContent).toContain("收容所：北投收容所");
  });

  it("confirms the animal, creates a pending handoff, and never persists the confirmation token", async () => {
    scanner.available.mockReturnValue(true);
    scanner.scan.mockResolvedValue("scanner-token-1234567890");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(candidate))
      .mockResolvedValueOnce(
        jsonResponse({
          ...candidate,
          confirmation_token: "confirmation-secret",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          id: "handoff-a",
          status: "pending",
          expires_at: "2026-08-25T13:15:00Z",
        }),
      );

    await renderPage(fetchMock);
    await clickButton("掃描動物 QR Code");
    await clickButton("確認並開始回報");

    expect(String(fetchMock.mock.calls[1][0])).toContain(
      "/v1/animals/animal-a/confirm",
    );
    expect(String(fetchMock.mock.calls[2][0])).toBe("/v1/care-report-handoffs");
    expect(
      JSON.parse(String((fetchMock.mock.calls[2][1] as RequestInit).body)),
    ).toEqual({
      animal_id: "animal-a",
      confirmation_token: "confirmation-secret",
      source: "liff_scan",
    });
    expect(container?.textContent).toContain("動物已確認");
    expect(container?.textContent).toContain("下一步請回到 LINE");
    expect(window.location.href).not.toContain("confirmation-secret");
    expect(
      JSON.stringify({ ...window.localStorage, ...window.sessionStorage }),
    ).not.toContain("confirmation-secret");
  });

  it("does not show success when handoff creation fails", async () => {
    window.history.replaceState(
      {},
      "",
      "/animal-confirmation?qr_token=direct-token-123456789",
    );
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(candidate))
      .mockResolvedValueOnce(
        jsonResponse({ ...candidate, confirmation_token: "short-lived" }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ message: "handoff failed" }, false, 503),
      );

    await renderPage(fetchMock);
    await clickButton("確認並開始回報");

    expect(container?.textContent).not.toContain("動物已確認");
    expect(container?.querySelector('[role="alert"]')?.textContent).toContain(
      "目前無法準備照護回報",
    );
  });

  it("keeps the latest scanned candidate when an older resolve returns late", async () => {
    scanner.available.mockReturnValue(true);
    scanner.scan
      .mockResolvedValueOnce("scanner-token-a-123456789")
      .mockResolvedValueOnce("scanner-token-b-123456789");
    let resolveA!: (response: Response) => void;
    const pendingA = new Promise<Response>((resolve) => {
      resolveA = resolve;
    });
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(pendingA)
      .mockResolvedValueOnce(
        jsonResponse({ ...candidate, id: "animal-b", name: "小白" }),
      );

    await renderPage(fetchMock);
    await clickButton("掃描動物 QR Code");
    await clickButton("掃描動物 QR Code");
    expect(container?.textContent).toContain("小白");

    await act(async () => {
      resolveA(jsonResponse({ ...candidate, name: "遲到的小黑" }));
      await flushEffects();
    });
    expect(container?.textContent).toContain("小白");
    expect(container?.textContent).not.toContain("遲到的小黑");
  });

  it("uses exact shelter-number lookup to reach the same confirmation card", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        items: [
          candidate,
          { ...candidate, id: "other", shelter_number: "A-0130" },
        ],
      }),
    );
    await renderPage(fetchMock);
    await clickButton("輸入完整收容編號");
    const input = container?.querySelector(
      "#exact-shelter-number",
    ) as HTMLInputElement;
    await act(async () => setInputValue(input, "A-013"));
    const form = container?.querySelector(
      'form[aria-label="exact-shelter-number-form"]',
    );
    await act(async () => {
      form?.dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
      await flushEffects();
    });
    expect(container?.textContent).toContain("確認照護動物");
    expect(container?.textContent).toContain("收容編號：A-013");
  });
});
