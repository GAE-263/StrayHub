// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import PlatformVolunteerRestrictionsPage from "./page";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

const pendingItem = {
  restriction: {
    id: "restriction-a",
    reason_category: "service_safety",
    starts_at: "2026-09-03T02:00:00Z",
    ends_at: null,
  },
  incident: {
    incident_type: "安全事件",
    severity: "high",
    factual_summary: "未依照牽繩安全流程",
    occurred_at: "2026-09-03T02:00:00Z",
  },
  originating_organization_name: "安心動物之家",
};

let root: Root | undefined;
let container: HTMLDivElement | undefined;

async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  container?.remove();
  container = undefined;
  vi.unstubAllGlobals();
});

async function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("React", React);
  vi.stubGlobal("fetch", fetchMock);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(<PlatformVolunteerRestrictionsPage />);
    await flush();
  });
}

describe("platform volunteer restriction review page", () => {
  it("shows pending incident context and removes an approved item", async () => {
    let items = [pendingItem];
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === "POST") {
          expect(JSON.parse(String(init.body))).toEqual({
            decision: "approve",
            reason: "平台管理員完成正式審查",
          });
          items = [];
          return response({ status: "active" });
        }
        return response(items);
      },
    );

    await renderPage(fetchMock);

    expect(container?.textContent).toContain("安心動物之家");
    expect(container?.textContent).toContain("未依照牽繩安全流程");
    const approve = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "核准平台限制");
    await act(async () => {
      approve?.click();
      await flush();
    });

    expect(container?.textContent).toContain("目前沒有待審查案件");
    expect(container?.textContent).not.toContain("未依照牽繩安全流程");
  });

  it("renders the API failure state", async () => {
    await renderPage(vi.fn(async () => response({}, 503)));

    expect(container?.textContent).toContain("無法載入平台志工限制審查");
  });
});
