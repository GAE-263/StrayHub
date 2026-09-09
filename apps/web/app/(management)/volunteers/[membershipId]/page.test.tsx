// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import VolunteerProfilePage from "./page";

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

type Note = {
  id: string;
  content: string;
  author_display_name: string;
  created_at: string;
};

const profile = {
  membership_id: "membership-a",
  volunteer_no: "V024",
  label: "黃・V024",
  membership_status: "active",
  can_assist_new_volunteers: false,
  statistics: {
    current_shelter_visits: 2,
    total_strayhub_visits: 8,
    visits_last_180_days: 6,
    visits_last_90_days: 4,
    visits_last_30_days: 1,
    last_visit_at: "2026-09-02T04:00:00Z",
    active_months_last_6_months: 4,
    recent_status: "consistently_active",
  },
  notes: [] as Note[],
  incidents: [],
  restrictions: [],
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
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
});

async function renderPage(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("React", React);
  vi.stubGlobal("fetch", fetchMock);
  window.sessionStorage.setItem("active_organization_id", "org-a");
  window.sessionStorage.setItem("access_token", "synthetic-token");
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(
      <VolunteerProfilePage
        params={Promise.resolve({ membershipId: "membership-a" })}
      />,
    );
    await flush();
  });
}

describe("volunteer profile page", () => {
  it("loads aggregate experience and updates optional management fields", async () => {
    let currentProfile = profile;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path.endsWith("/assist-flag")) {
          currentProfile = {
            ...currentProfile,
            can_assist_new_volunteers: true,
          };
          return response({ can_assist_new_volunteers: true });
        }
        if (path.endsWith("/notes")) {
          expect(init?.method).toBe("POST");
          expect(JSON.parse(String(init?.body))).toEqual({
            content: "熟悉犬舍流程",
          });
          currentProfile = {
            ...currentProfile,
            notes: [
              {
                id: "note-a",
                content: "熟悉犬舍流程",
                author_display_name: "你",
                created_at: "2026-09-04T01:00:00Z",
              },
            ],
          };
          return response(currentProfile.notes[0], 201);
        }
        return response(currentProfile);
      },
    );

    await renderPage(fetchMock);

    expect(container?.textContent).toContain("黃・V024");
    expect(container?.textContent).toContain("StrayHub 累積");
    expect(container?.textContent).toContain("8 次");
    expect(container?.textContent).toContain("持續參與");

    const assist = Array.from(container?.querySelectorAll("button") ?? []).find(
      (button) => button.textContent?.includes("標記為可協助新人"),
    );
    await act(async () => {
      assist?.click();
      await flush();
    });
    expect(container?.textContent).toContain("取消「可協助新人」");

    const textarea =
      container?.querySelector<HTMLTextAreaElement>("#volunteer-note");
    await act(async () => {
      if (textarea) {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype,
          "value",
        )?.set;
        setter?.call(textarea, "熟悉犬舍流程");
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });
    const addNote = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "新增備註");
    await act(async () => {
      addNote?.click();
      await flush();
    });

    expect(container?.textContent).toContain("熟悉犬舍流程");
    expect(
      fetchMock.mock.calls.some(([input]) => String(input).endsWith("/notes")),
    ).toBe(true);
  });

  it("shows a recoverable load error without exposing stale profile data", async () => {
    await renderPage(vi.fn(async () => response({}, 503)));

    expect(container?.textContent).toContain("無法載入志工資料");
    expect(container?.textContent).not.toContain("黃・V024");
  });
});
