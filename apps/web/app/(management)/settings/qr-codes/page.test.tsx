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

const activeQr = {
  id: "qr-1",
  animal_id: "animal-12345678",
  status: "active",
  revoked: false,
  deep_link: "https://example.test/qr/qr-1",
  token: null,
};

const revokedQr = {
  ...activeQr,
  id: "qr-2",
  animal_id: "animal-revoked-12345678",
  status: "revoked",
  revoked: true,
  deep_link: null,
};

const legacyActiveQr = {
  ...activeQr,
  id: "qr-3",
  animal_id: "animal-legacy-12345678",
  deep_link: null,
};

const adminProfile = {
  user: {
    id: "user-a",
    platform_role: null,
    status: "active",
  },
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

let root: Root | undefined;
let container: HTMLDivElement | undefined;

async function renderPage(profile = adminProfile) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith("/auth/active-shelter-context"))
        return response({ organization_id: "org-a" });
      if (path.endsWith("/auth/me")) return response(profile);
      if (path.endsWith("/revoke")) {
        return response({ ...activeQr, revoked: true, status: "revoked" });
      }
      if (path.endsWith("/regenerate")) return response(activeQr);
      if (path.endsWith("/qr-codes") && !init?.method)
        return response({ items: [activeQr, legacyActiveQr, revokedQr] });
      return response({}, 404);
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

describe("care QR management actions", () => {
  it("removes UUID creation and uses the care QR management copy", async () => {
    await renderPage();

    expect(container?.querySelector("h1")?.textContent).toBe("照護 QR 管理");
    expect(container?.querySelector("input")).toBeNull();
    expect(container?.querySelector("form")).toBeNull();
    expect(container?.textContent).not.toContain("Animal ID");
    expect(container?.textContent).not.toContain("已建立綁定");
    expect(container?.textContent).toContain("QR 紀錄");
  });

  it("shows the active lifecycle actions to an admin", async () => {
    await renderPage();
    const activeRow = Array.from(container?.querySelectorAll("tr") ?? []).find(
      (row) => row.textContent?.includes("animal-1"),
    );

    expect(activeRow?.textContent).toContain("前往重新列印");
    expect(activeRow?.textContent).toContain("重新產生新 QR");
    expect(activeRow?.textContent).toContain("撤銷 QR");
  });

  it("keeps revoked records read-only with a link to the animal profile", async () => {
    await renderPage();
    const revokedRow = Array.from(container?.querySelectorAll("tr") ?? []).find(
      (row) => row.textContent?.includes("animal-r"),
    );
    const link = revokedRow?.querySelector("a");

    expect(revokedRow?.textContent).toContain("前往動物檔案");
    expect(revokedRow?.textContent).not.toContain("重新產生");
    expect(revokedRow?.textContent).not.toContain("撤銷");
    expect(link?.getAttribute("href")).toBe("/animals/animal-revoked-12345678");
  });

  it("does not offer reprint for an active legacy QR without a printable link", async () => {
    await renderPage();
    const legacyRow = Array.from(container?.querySelectorAll("tr") ?? []).find(
      (row) => row.textContent?.includes("animal-l"),
    );

    expect(legacyRow?.textContent).toContain("舊版 QR 無法重新列印");
    expect(legacyRow?.textContent).toContain("重新產生新 QR");
    expect(legacyRow?.textContent).toContain("撤銷 QR");
    expect(legacyRow?.querySelector("a")).toBeNull();
  });

  it("does not expose admin mutations to staff", async () => {
    await renderPage(staffProfile);

    expect(container?.textContent).toContain("前往重新列印");
    expect(container?.textContent).not.toContain("重新產生新 QR");
    expect(container?.textContent).not.toContain("撤銷 QR");
  });

  it("requires destructive confirmation before revoking a QR token", async () => {
    await renderPage();
    const revokeButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "撤銷 QR");

    await act(async () => revokeButton?.click());

    expect(container?.textContent).toContain("確認撤銷 QR");
    expect(container?.textContent).toContain("animal-12345678");
    expect(container?.textContent).toContain("不會建立新的 QR");
    expect(container?.textContent).toContain("立即失效");
    expect(revokeButton?.classList.contains("ui-button-destructive")).toBe(
      true,
    );
  });
});
