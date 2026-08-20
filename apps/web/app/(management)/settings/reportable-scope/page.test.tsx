// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import ReportableScopePage from "./page";

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

const scope = {
  id: "scope-1",
  animal_id: "animal-12345678",
  area_id: null,
  volunteer_user_id: "volunteer-1",
  starts_at: "2026-08-19T00:00:00Z",
  ends_at: "2026-08-20T00:00:00Z",
  status: "active",
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
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/scope-1"))
        return response({ ...scope, status: "inactive" });
      return response({ items: [scope] });
    }),
  );
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(<ReportableScopePage />);
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

describe("reportable scope governance actions", () => {
  it("requires confirmation before deactivating a reportable scope", async () => {
    await renderPage();
    const deactivateButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "停用");

    await act(async () => deactivateButton?.click());

    expect(container?.textContent).toContain("確認停用可回報範圍");
    expect(container?.textContent).toContain("animal-12345678");
    expect(container?.textContent).toContain("2026");
    expect(container?.textContent).toContain("志工");
  });
});
