// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import ArchivedShelterMembershipsPage from "./page";

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

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

let root: Root | undefined;
let container: HTMLDivElement | undefined;

async function renderPage() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.endsWith("/auth/me")) {
      return jsonResponse({
        user: { id: "user-a", status: "active" },
        memberships: [
          {
            id: "membership-a",
            organization_id: "org-a",
            role: "SHELTER_ADMIN",
            status: "active",
          },
        ],
      });
    }
    if (path.endsWith("/organizations")) {
      return jsonResponse({
        items: [{ id: "org-a", name: "收容所 A", status: "active" }],
      });
    }
    if (path.endsWith("/memberships/archived")) {
      return jsonResponse({
        items: [
          {
            id: "membership-staff",
            user_id: "user-staff",
            display_name: "已封存工作人員",
            username: "archived-staff",
            role: "STAFF",
            status: "archived",
            access_version: 1,
            archived_from_status: "disabled",
          },
          {
            id: "membership-volunteer",
            user_id: "user-volunteer",
            display_name: "已封存志工",
            username: "archived-volunteer",
            role: "VOLUNTEER",
            status: "archived",
            access_version: 1,
          },
        ],
      });
    }
    if (path.endsWith("/memberships")) {
      return jsonResponse({
        items: [
          {
            id: "membership-admin",
            role: "SHELTER_ADMIN",
            status: "active",
          },
        ],
      });
    }
    return jsonResponse({});
  });
  vi.stubGlobal("fetch", fetchMock);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(<ArchivedShelterMembershipsPage />);
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

describe("archived shelter memberships page", () => {
  it("shows archived members in separate staff and volunteer sections", async () => {
    await renderPage();

    expect(container?.textContent).toContain("已封存成員");
    expect(container?.textContent).toContain("已封存工作人員");
    expect(container?.textContent).toContain("已封存志工");
    expect(container?.textContent).toContain("工作人員");
    expect(container?.textContent).not.toContain("管理人員");
    expect(container?.textContent).toContain("封存前：已停用");
    expect(container?.textContent).toContain("恢復成員");
    const restoreButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "恢復成員");
    await act(async () => restoreButton?.click());
    expect(container?.querySelector('[role="alertdialog"]')).not.toBeNull();
    expect(container?.textContent).toContain("確認權限調整");
    const cancelButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "取消");
    await act(async () => cancelButton?.click());
    expect(
      container?.querySelector<HTMLDialogElement>('[role="alertdialog"]')?.open,
    ).toBe(false);
    const sectionTitles = Array.from(
      container?.querySelectorAll(".membership-section h2") ?? [],
    ).map((heading) => heading.textContent?.trim());
    expect(sectionTitles).toEqual(["志工", "工作人員"]);
  });
});
