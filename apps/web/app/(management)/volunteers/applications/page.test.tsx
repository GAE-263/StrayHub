// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import VolunteerApplicationsPage from "./page";
import { selectInitialServiceDate } from "./review-date";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

function response(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response;
}

function localDate(value: Date): string {
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${value.getFullYear()}-${month}-${day}`;
}

async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

let root: Root | undefined;
let container: HTMLDivElement | undefined;

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  container?.remove();
  container = undefined;
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe("volunteer application review date", () => {
  it("reloads current list and calendar after completed date-scoped rejection", async () => {
    const today = localDate(new Date());
    let listCall = 0;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input), "http://localhost");
        if (url.pathname.endsWith("/volunteer-decision-batches")) {
          return response({
            id: "batch-a",
            status: "queued",
            requested_count: 1,
            processed_count: 0,
            succeeded_count: 0,
            conflict_count: 0,
            failed_count: 0,
          });
        }
        if (url.pathname.endsWith("/batch-a")) {
          return response({
            id: "batch-a",
            status: "completed",
            requested_count: 1,
            processed_count: 1,
            succeeded_count: 1,
            conflict_count: 0,
            failed_count: 0,
          });
        }
        if (url.pathname.endsWith("/batch-a/items")) {
          return response({
            items: [
              {
                application_id: "application-a",
                expected_version: 1,
                result: "succeeded",
              },
            ],
            next_cursor: null,
          });
        }
        listCall += 1;
        if (init?.method === "POST") return response({});
        if (listCall === 1) {
          return response({
            items: [
              {
                id: "application-a",
                display_name: "LINE 志工",
                status: "pending",
                version: 1,
              },
            ],
            matching_count: 1,
            review_calendar: [
              { service_date: today, pending_count: 1 },
              { service_date: "2026-08-26", pending_count: 1 },
            ],
            available_service_dates: [],
          });
        }
        return response({
          items: [],
          matching_count: 0,
          review_calendar: [{ service_date: "2026-08-26", pending_count: 1 }],
          available_service_dates: [],
        });
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("React", React);
    window.sessionStorage.setItem("access_token", "local-token");
    window.sessionStorage.setItem("active_organization_id", "org-a");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<VolunteerApplicationsPage />);
      await flush();
    });
    expect(container.textContent).toContain("LINE 志工");
    const checkbox = container!.querySelector(
      'input[aria-label="選取 LINE 志工"]',
    ) as HTMLInputElement;
    await act(async () => checkbox.click());
    const decision = container!.querySelector("select") as HTMLSelectElement;
    await act(async () => {
      decision.value = "reject";
      decision.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const reason = container!.querySelector(
      'input[aria-label="拒絕原因"]',
    ) as HTMLInputElement;
    await act(async () => {
      reason.value = "診斷用原因";
      reason.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () =>
      Array.from(container!.querySelectorAll("button"))
        .find((button) => button.textContent?.includes("確認並建立批次"))
        ?.click(),
    );
    await act(async () =>
      Array.from(container!.querySelectorAll("button"))
        .find((button) => button.textContent?.includes("送出完整快照"))
        ?.click(),
    );
    await act(async () =>
      Array.from(container!.querySelectorAll("button"))
        .find((button) => button.textContent?.includes("更新進度"))
        ?.click(),
    );
    await flush();

    expect(listCall).toBe(2);
    expect(container.textContent).not.toContain("LINE 志工");
    expect(container.textContent).toContain("2026-08-26");
  });

  it("selects the nearest future date that has pending applications when today is empty", () => {
    expect(
      selectInitialServiceDate("2026-08-24", [
        { service_date: "2026-08-25", pending_count: 1 },
        { service_date: "2026-08-26", pending_count: 1 },
      ]),
    ).toBe("2026-08-25");
  });

  it("keeps today selected when today has pending applications", () => {
    expect(
      selectInitialServiceDate("2026-08-24", [
        { service_date: "2026-08-24", pending_count: 2 },
        { service_date: "2026-08-25", pending_count: 1 },
      ]),
    ).toBe("2026-08-24");
  });

  it("loads the selected calendar date and keeps decisions date-scoped", async () => {
    const today = localDate(new Date());
    const selectedDate = "2099-08-25";
    const requestedDates: string[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      requestedDates.push(url.searchParams.get("service_date") ?? "");
      return response({
        items: [],
        matching_count: 0,
        next_cursor: null,
        review_calendar: [
          { service_date: today, pending_count: 1 },
          { service_date: selectedDate, pending_count: 2 },
        ],
        available_service_dates: [],
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("React", React);
    window.sessionStorage.setItem("access_token", "local-token");
    window.sessionStorage.setItem("active_organization_id", "org-a");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<VolunteerApplicationsPage />);
      await flush();
    });
    const dateButton = container.querySelector(
      `button[aria-label^="${selectedDate}"]`,
    ) as HTMLButtonElement;
    expect(dateButton).toBeTruthy();

    await act(async () => {
      dateButton.click();
      await flush();
    });

    expect(requestedDates).toEqual([today, selectedDate]);
    expect(
      (container.querySelector('input[type="date"]') as HTMLInputElement).value,
    ).toBe(selectedDate);
  });

  it("reloads the list for the nearest pending date", async () => {
    const today = localDate(new Date());
    const nextDateValue = new Date();
    nextDateValue.setDate(nextDateValue.getDate() + 1);
    const nextDate = localDate(nextDateValue);
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      const selectedDate = url.searchParams.get("service_date");
      if (selectedDate === nextDate) {
        return response({
          items: [
            {
              id: "application-a",
              display_name: "LINE 志工",
              status: "pending",
              version: 1,
            },
          ],
          matching_count: 1,
          next_cursor: null,
          available_service_dates: [
            { service_date: nextDate, pending_count: 1 },
          ],
        });
      }
      expect(selectedDate).toBe(today);
      return response({
        items: [],
        matching_count: 0,
        next_cursor: null,
        available_service_dates: [{ service_date: nextDate, pending_count: 1 }],
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("React", React);
    window.sessionStorage.setItem("access_token", "local-token");
    window.sessionStorage.setItem("active_organization_id", "org-a");

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(<VolunteerApplicationsPage />);
      await flush();
    });

    expect(
      (container.querySelector('input[type="date"]') as HTMLInputElement).value,
    ).toBe(nextDate);
    expect(container.textContent).toContain("LINE 志工");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not let an older date response replace the current list", async () => {
    const today = localDate(new Date());
    let resolveToday: ((value: Response) => void) | undefined;
    const todayResponse = new Promise<Response>((resolve) => {
      resolveToday = resolve;
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      if (url.searchParams.get("service_date") === today) return todayResponse;
      return response({
        items: [
          {
            id: "new",
            display_name: "較新申請",
            status: "pending",
            version: 1,
          },
        ],
        matching_count: 1,
        next_cursor: null,
        available_service_dates: [],
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("React", React);
    window.sessionStorage.setItem("access_token", "local-token");
    window.sessionStorage.setItem("active_organization_id", "org-a");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => root?.render(<VolunteerApplicationsPage />));
    const input = container.querySelector(
      'input[type="date"]',
    ) as HTMLInputElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )?.set?.call(input, "2026-08-26");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container
        ?.querySelector("form")
        ?.dispatchEvent(
          new Event("submit", { bubbles: true, cancelable: true }),
        );
      await flush();
    });
    resolveToday?.(
      response({
        items: [
          { id: "old", display_name: "舊申請", status: "pending", version: 1 },
        ],
        matching_count: 1,
        next_cursor: null,
        available_service_dates: [],
      }),
    );
    await act(flush);

    expect(container.textContent).toContain("較新申請");
    expect(container.textContent).not.toContain("舊申請");
  });

  it("does not let an older request error replace a newer successful list", async () => {
    const today = localDate(new Date());
    let rejectToday: ((reason: Error) => void) | undefined;
    const todayResponse = new Promise<Response>((_resolve, reject) => {
      rejectToday = reject;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input), "http://localhost");
        if (url.searchParams.get("service_date") === today)
          return todayResponse;
        return response({
          items: [
            {
              id: "new",
              display_name: "較新申請",
              status: "pending",
              version: 1,
            },
          ],
          matching_count: 1,
          next_cursor: null,
          available_service_dates: [],
        });
      }),
    );
    vi.stubGlobal("React", React);
    window.sessionStorage.setItem("access_token", "local-token");
    window.sessionStorage.setItem("active_organization_id", "org-a");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => root?.render(<VolunteerApplicationsPage />));
    const input = container.querySelector(
      'input[type="date"]',
    ) as HTMLInputElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )?.set?.call(input, "2026-08-26");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container
        ?.querySelector("form")
        ?.dispatchEvent(
          new Event("submit", { bubbles: true, cancelable: true }),
        );
      await flush();
    });
    rejectToday?.(new Error("stale failure"));
    await act(flush);

    expect(container.textContent).toContain("較新申請");
    expect(container.textContent).not.toContain("stale failure");
  });

  it("clears the prior date rows when the replacement load fails", async () => {
    const today = localDate(new Date());
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      if (url.searchParams.get("service_date") === today) {
        return response({
          items: [
            {
              id: "old",
              display_name: "舊日期申請",
              status: "pending",
              version: 1,
            },
          ],
          matching_count: 1,
          next_cursor: null,
          available_service_dates: [],
        });
      }
      throw new Error("replacement failed");
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("React", React);
    window.sessionStorage.setItem("access_token", "local-token");
    window.sessionStorage.setItem("active_organization_id", "org-a");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(<VolunteerApplicationsPage />);
      await flush();
    });
    expect(container.textContent).toContain("舊日期申請");
    const input = container.querySelector(
      'input[type="date"]',
    ) as HTMLInputElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )?.set?.call(input, "2026-08-26");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container
        ?.querySelector("form")
        ?.dispatchEvent(
          new Event("submit", { bubbles: true, cancelable: true }),
        );
      await flush();
    });

    expect(container.textContent).toContain("replacement failed");
    expect(container.textContent).not.toContain("舊日期申請");
  });

  it("clears loaded rows as soon as the review date changes", async () => {
    const today = localDate(new Date());
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        response({
          items: [
            {
              id: "old",
              display_name: "舊日期申請",
              status: "pending",
              version: 1,
            },
          ],
          matching_count: 1,
          next_cursor: null,
          available_service_dates: [{ service_date: today, pending_count: 1 }],
        }),
      ),
    );
    vi.stubGlobal("React", React);
    window.sessionStorage.setItem("access_token", "local-token");
    window.sessionStorage.setItem("active_organization_id", "org-a");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(<VolunteerApplicationsPage />);
      await flush();
    });
    expect(container.textContent).toContain("舊日期申請");

    const input = container.querySelector(
      'input[type="date"]',
    ) as HTMLInputElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )?.set?.call(input, "2026-08-26");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });

    expect(container.textContent).not.toContain("舊日期申請");
  });
});
