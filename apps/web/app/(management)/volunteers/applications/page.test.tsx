// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import VolunteerApplicationsPage from "./page";
import { selectInitialServiceDate } from "./review-date";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

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
        available_service_dates: [
          { service_date: nextDate, pending_count: 1 },
        ],
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
        items: [{ id: "new", display_name: "較新申請", status: "pending", version: 1 }],
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
    const input = container.querySelector('input[type="date"]') as HTMLInputElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(
        input,
        "2026-08-26",
      );
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container?.querySelector("form")?.dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
      await flush();
    });
    resolveToday?.(
      response({
        items: [{ id: "old", display_name: "舊申請", status: "pending", version: 1 }],
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
        if (url.searchParams.get("service_date") === today) return todayResponse;
        return response({
          items: [{ id: "new", display_name: "較新申請", status: "pending", version: 1 }],
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
    const input = container.querySelector('input[type="date"]') as HTMLInputElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(
        input,
        "2026-08-26",
      );
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container?.querySelector("form")?.dispatchEvent(
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
          items: [{ id: "old", display_name: "舊日期申請", status: "pending", version: 1 }],
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
    const input = container.querySelector('input[type="date"]') as HTMLInputElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(
        input,
        "2026-08-26",
      );
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container?.querySelector("form")?.dispatchEvent(
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
          items: [{ id: "old", display_name: "舊日期申請", status: "pending", version: 1 }],
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

    const input = container.querySelector('input[type="date"]') as HTMLInputElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(
        input,
        "2026-08-26",
      );
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });

    expect(container.textContent).not.toContain("舊日期申請");
  });
});
