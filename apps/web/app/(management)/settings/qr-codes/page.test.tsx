// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import QrCodesPage from "./page";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

if (!HTMLDialogElement.prototype.showModal) {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value() {
      this.open = true;
    },
  });
}

if (!HTMLDialogElement.prototype.close) {
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value() {
      this.open = false;
    },
  });
}

const qr = {
  id: "qr-1",
  animal_id: "animal-12345678",
  status: "active",
  revoked: false,
  deep_link: "https://example.test/qr/qr-1",
  token: null,
};

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

let root: Root | undefined;
let container: HTMLDivElement | undefined;

async function renderPage() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith("/qr-codes") && init?.method === "POST") {
        return response({ ...qr, token: "new-token" });
      }
      if (path.endsWith("/revoke")) {
        return response({ ...qr, revoked: true, status: "revoked" });
      }
      return response({ items: [qr] });
    }),
  );
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(<QrCodesPage />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  container?.remove();
  container = undefined;
  vi.unstubAllGlobals();
});

describe("QR binding governance actions", () => {
  it("requires destructive confirmation before revoking a QR token", async () => {
    await renderPage();
    const revokeButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "撤銷");

    await act(async () => revokeButton?.click());

    expect(container?.textContent).toContain("確認撤銷 QR");
    expect(container?.textContent).toContain("animal-12345678");
    expect(container?.textContent).toContain("舊標籤需要更換");
    expect(container?.textContent).toContain("立即失效");
    expect(revokeButton?.classList.contains("ui-button-destructive")).toBe(
      true,
    );
  });
});
