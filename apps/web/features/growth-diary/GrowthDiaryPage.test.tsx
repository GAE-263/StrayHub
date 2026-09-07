// @vitest-environment jsdom

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchGrowthDiaryEntries, GrowthDiaryApiError } from "./api";
import { GrowthDiaryPage, GrowthDiaryPageView } from "./GrowthDiaryPage";
import type { GrowthDiaryListResponse } from "./types";

const emptyPage: GrowthDiaryListResponse = {
  items: [],
  page: 1,
  page_size: 50,
  total: 0,
  timezone: "Asia/Taipei",
};

vi.mock("./api", async (importOriginal) => {
  const original = await importOriginal<typeof import("./api")>();
  return { ...original, fetchGrowthDiaryEntries: vi.fn() };
});

const fetchEntries = vi.mocked(fetchGrowthDiaryEntries);

beforeEach(() => {
  fetchEntries.mockReset();
  fetchEntries.mockResolvedValue(emptyPage);
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe("GrowthDiaryPageView", () => {
  it("shows a clear loading state", () => {
    const html = renderToStaticMarkup(
      <GrowthDiaryPageView state="loading" data={null} />,
    );
    expect(html).toContain("正在整理毛孩日記");
  });

  it("distinguishes a truly empty diary from an error", () => {
    const empty = renderToStaticMarkup(
      <GrowthDiaryPageView state="ready" data={emptyPage} />,
    );
    const error = renderToStaticMarkup(
      <GrowthDiaryPageView
        state="error"
        data={null}
        onRetry={() => undefined}
      />,
    );

    expect(empty).toContain("還沒有毛孩日記");
    expect(empty).toContain("領養人分享近況後，日記會依時間出現在這裡");
    expect(error).toContain("目前無法載入毛孩日記");
    expect(error).toContain("重新載入");
  });

  it("distinguishes filtered empty results and offers to clear filters", () => {
    const html = renderToStaticMarkup(
      <GrowthDiaryPageView
        state="ready"
        data={emptyPage}
        hasActiveFilters
        onClearFilters={() => undefined}
      />,
    );

    expect(html).toContain("找不到符合條件的日記");
    expect(html).toContain("清除搜尋與篩選");
    expect(html).not.toContain("還沒有毛孩日記");
  });

  it("submits server-side filters, resets page, and aborts the stale request", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => root.render(<GrowthDiaryPage />));

    const input = container.querySelector<HTMLInputElement>(
      "#growth-diary-query",
    );
    const select =
      container.querySelector<HTMLSelectElement>("#growth-diary-mood");
    const form = container.querySelector("form");
    expect(input).not.toBeNull();
    expect(select).not.toBeNull();

    await act(async () => {
      const inputSetter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )?.set;
      inputSetter?.call(input, "  米糕  ");
      input?.dispatchEvent(new Event("input", { bubbles: true }));
      input?.dispatchEvent(new Event("change", { bubbles: true }));
      const selectSetter = Object.getOwnPropertyDescriptor(
        HTMLSelectElement.prototype,
        "value",
      )?.set;
      selectSetter?.call(select, "concern");
      select?.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => {
      form?.dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
    });

    expect(fetchEntries).toHaveBeenLastCalledWith(
      {
        query: "米糕",
        mood: "concern",
        status: "all",
        fromDate: "",
        toDate: "",
        page: 1,
        pageSize: 20,
      },
      expect.any(AbortSignal),
    );
    expect(fetchEntries.mock.calls[0][1]?.aborted).toBe(true);
    await act(async () => root.unmount());
  });

  it("shows a safe permission state for 403 without leaking backend detail", async () => {
    fetchEntries.mockRejectedValueOnce(
      new GrowthDiaryApiError("internal policy detail", 403),
    );
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () => root.render(<GrowthDiaryPage />));

    expect(container.textContent).toContain("沒有查看毛孩日記的權限");
    expect(container.textContent).not.toContain("internal policy detail");
    expect(container.textContent).not.toContain("重新載入");
    await act(async () => root.unmount());
  });

  it("retries a network error using a fresh request", async () => {
    fetchEntries
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(emptyPage);
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () => root.render(<GrowthDiaryPage />));
    expect(container.textContent).toContain("目前無法載入毛孩日記");
    const retry = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "重新載入",
    );
    await act(async () => retry?.click());

    expect(fetchEntries).toHaveBeenCalledTimes(2);
    expect(fetchEntries.mock.calls[0][1]).not.toBe(
      fetchEntries.mock.calls[1][1],
    );
    expect(container.textContent).toContain("還沒有毛孩日記");
    await act(async () => root.unmount());
  });
});
