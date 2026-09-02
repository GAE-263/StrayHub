// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AnimalCareQrCard } from "./AnimalCareQrCard";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("qrcode.react", () => ({
  QRCodeSVG: ({ value, title }: { value: string; title: string }) => (
    <svg aria-label={title} data-value={value} />
  ),
}));

const animal = {
  id: "animal-a",
  organizationId: "org-a",
  name: "小黑",
  shelterNumber: "A-013",
  status: "active",
  areaName: "犬舍 A3",
};

const qr = {
  id: "qr-a",
  organization_id: "org-a",
  animal_id: "animal-a",
  status: "active",
  revoked: false,
  token: null,
  deep_link:
    "/animal-confirmation?organization_id=org-a&qr_token=opaque-locator-123456",
};

const adminProfile = {
  user: { id: "user-a", platform_role: null, status: "active" },
  memberships: [
    {
      id: "membership-a",
      organization_id: "org-a",
      user_id: "user-a",
      role: "SHELTER_ADMIN",
      status: "active",
    },
  ],
};

const staffProfile = {
  ...adminProfile,
  memberships: [
    {
      ...adminProfile.memberships[0],
      role: "STAFF",
    },
  ],
};

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

async function flush() {
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
}

let root: Root | undefined;
let container: HTMLDivElement | undefined;

async function renderCard(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(<AnimalCareQrCard animal={animal} />);
    await flush();
  });
}

async function click(label: string) {
  const button = Array.from(container?.querySelectorAll("button") ?? []).find(
    (item) => item.textContent?.includes(label),
  );
  expect(button).toBeInstanceOf(HTMLButtonElement);
  await act(async () => {
    (button as HTMLButtonElement).click();
    await flush();
  });
}

beforeEach(() => {
  window.sessionStorage.setItem("access_token", "test-token");
  vi.stubGlobal("print", vi.fn());
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
});

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  container?.remove();
  container = undefined;
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

describe("animal care QR card", () => {
  it("shows the create action to an admin when no active QR exists", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({ items: [] }))
      .mockResolvedValueOnce(
        response({
          organization_id: "org-a",
          organization_name: "虛構收容所 A",
        }),
      )
      .mockResolvedValueOnce(response(adminProfile));
    await renderCard(fetchMock);

    expect(container?.textContent).toContain("尚未建立照護 QR Code");
    expect(container?.textContent).toContain("建立照護 QR");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("keeps QR information read-only for staff", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({ items: [qr] }))
      .mockResolvedValueOnce(
        response({
          organization_id: "org-a",
          organization_name: "虛構收容所 A",
        }),
      )
      .mockResolvedValueOnce(response(staffProfile));
    await renderCard(fetchMock);

    expect(container?.querySelector("svg")).not.toBeNull();
    expect(container?.textContent).toContain("重新列印");
    expect(container?.textContent).not.toContain("建立照護 QR");
    expect(container?.textContent).not.toContain("重新產生新 QR");
  });

  it("generates only after click and shows a scannable preview without raw token text", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({ items: [] }))
      .mockResolvedValueOnce(
        response({
          organization_id: "org-a",
          organization_name: "虛構收容所 A",
        }),
      )
      .mockResolvedValueOnce(response(adminProfile))
      .mockResolvedValueOnce(response(qr, 201));
    await renderCard(fetchMock);
    await click("建立照護 QR");

    const svg = container?.querySelector("svg");
    expect(svg?.getAttribute("aria-label")).toBe("小黑的照護回報 QR Code");
    expect(svg?.getAttribute("data-value")).toContain("/animal-confirmation?");
    expect(container?.textContent).toContain("小黑");
    expect(container?.textContent).toContain("A-013");
    expect(container?.textContent).toContain("虛構收容所 A");
    expect(container?.textContent).not.toContain("opaque-locator-123456");
    expect(fetchMock.mock.calls[3][1]?.method).toBe("POST");
  });

  it("reuses an existing active QR without auto-creating another", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({ items: [qr] }))
      .mockResolvedValueOnce(
        response({
          organization_id: "org-a",
          organization_name: "虛構收容所 A",
        }),
      )
      .mockResolvedValueOnce(response(adminProfile));
    await renderCard(fetchMock);

    expect(container?.querySelector("svg")).not.toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(
      fetchMock.mock.calls.some((call) => call[1]?.method === "POST"),
    ).toBe(false);
  });

  it("reprints without a mutation and warns that regeneration invalidates the current QR", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({ items: [qr] }))
      .mockResolvedValueOnce(
        response({
          organization_id: "org-a",
          organization_name: "虛構收容所 A",
        }),
      )
      .mockResolvedValueOnce(response(adminProfile));
    await renderCard(fetchMock);

    await click("重新列印");
    expect(window.print).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(
      fetchMock.mock.calls.some((call) => call[1]?.method === "POST"),
    ).toBe(false);

    await click("重新產生新 QR");
    expect(container?.textContent).toContain("目前的 QR 會立即失效");
    expect(container?.textContent).toContain("更換現場舊標籤");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("shows non-persistent physical label guidance after regeneration", async () => {
    const replacement = { ...qr, id: "qr-b" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({ items: [qr] }))
      .mockResolvedValueOnce(
        response({
          organization_id: "org-a",
          organization_name: "虛構收容所 A",
        }),
      )
      .mockResolvedValueOnce(response(adminProfile))
      .mockResolvedValueOnce(response(replacement));
    await renderCard(fetchMock);

    await click("重新產生新 QR");
    await click("確認重新產生新 QR");

    expect(container?.textContent).toContain("新 QR 已建立，舊 QR 已失效");
    expect(container?.textContent).toContain("列印新的 QR 標籤");
    expect(container?.textContent).toContain("移除舊標籤");
    expect(container?.textContent).toContain("將新標籤貼至正確籠位");
    expect(fetchMock.mock.calls[3][1]?.method).toBe("POST");
  });

  it("rejects a foreign-tenant QR response and renders no preview", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        response({ items: [{ ...qr, organization_id: "org-b" }] }),
      )
      .mockResolvedValueOnce(
        response({
          organization_id: "org-a",
          organization_name: "虛構收容所 A",
        }),
      )
      .mockResolvedValueOnce(response(adminProfile));
    await renderCard(fetchMock);

    expect(container?.querySelector("svg")).toBeNull();
    expect(container?.querySelector('[role="alert"]')?.textContent).toContain(
      "目前無法載入照護 QR Code",
    );
  });
});
