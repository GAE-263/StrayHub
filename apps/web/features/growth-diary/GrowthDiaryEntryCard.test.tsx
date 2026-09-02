// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchGrowthDiaryDetail } from "./api";
import { GrowthDiaryEntryCard } from "./GrowthDiaryEntryCard";
import type { GrowthDiaryDetail, GrowthDiaryListItem } from "./types";

vi.mock("./api", async (importOriginal) => {
  const original = await importOriginal<typeof import("./api")>();
  return { ...original, fetchGrowthDiaryDetail: vi.fn() };
});

const fetchDetail = vi.mocked(fetchGrowthDiaryDetail);

beforeEach(() => {
  fetchDetail.mockReset();
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

function entry(
  status: GrowthDiaryListItem["ai_analysis"]["status"],
  mood: GrowthDiaryListItem["ai_analysis"]["mood"] = null,
): GrowthDiaryListItem {
  return {
    id: "08aa6641-2222-4333-8444-555555555555",
    inquiry_id: "18aa6641-2222-4333-8444-555555555555",
    animal_id: "28aa6641-2222-4333-8444-555555555555",
    animal_name: "米糕",
    shelter_number: "A-0241",
    has_photo: false,
    photo_endpoint: null,
    note: "這兩天米糕吃得比較少，但散步也走一下就想回家。",
    ai_analysis: {
      status,
      provenance_status: status === "legacy" ? "legacy_missing" : "unavailable",
      mood,
      adopter_reply: null,
      staff_summary: mood === "concern" ? "食慾與活動力同時下降。" : null,
    },
    created_at: "2026-09-02T09:42:00+08:00",
  };
}

describe("GrowthDiaryEntryCard", () => {
  it("separates adopter content from AI-derived content", () => {
    const html = renderToStaticMarkup(
      <GrowthDiaryEntryCard entry={entry("succeeded", "concern")} />,
    );

    expect(html).toContain("領養人原文");
    expect(html).toContain("AI 追蹤摘要");
    expect(html).toContain("AI 產生、未經人工確認，並非醫療診斷");
    expect(html).toContain("AI 建議人工查看");
    expect(html).toContain("食慾與活動力同時下降");
  });

  it.each([
    ["pending", "等待分析"],
    ["failed", "尚無分析"],
    ["unconfigured", "尚無分析"],
    ["not_applicable", "這篇日記沒有可分析的文字"],
    ["legacy", "來源資訊未留存"],
  ] as const)("keeps original content visible for %s", (status, copy) => {
    const html = renderToStaticMarkup(
      <GrowthDiaryEntryCard entry={entry(status)} />,
    );

    expect(html).toContain("這兩天米糕吃得比較少");
    expect(html).toContain(copy);
  });

  it("loads provenance only after disclosure is expanded", async () => {
    const listEntry = entry("succeeded", "positive");
    const detail: GrowthDiaryDetail = {
      ...listEntry,
      ai_provenance: {
        provenance_status: "available",
        provider: "google_gemini",
        model_name: "gemini-test",
        model_version: "gemini-test",
        prompt_version: "growth-diary-v1",
        output_schema_version: "growth-diary-analysis-v1",
        analyzed_at: "2026-09-02T09:43:00+08:00",
      },
      ai_raw_output: { raw: "detail-only-secret" },
    };
    fetchDetail.mockResolvedValue(detail);
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () =>
      root.render(<GrowthDiaryEntryCard entry={listEntry} />),
    );
    expect(fetchDetail).not.toHaveBeenCalled();
    expect(container.textContent).not.toContain("detail-only-secret");

    const button = container.querySelector("button");
    expect(button?.textContent).toContain("查看 AI 來源");
    await act(async () => button?.click());

    expect(fetchDetail).toHaveBeenCalledOnce();
    expect(fetchDetail).toHaveBeenCalledWith(
      listEntry.id,
      expect.any(AbortSignal),
    );
    expect(container.textContent).toContain("gemini-test");
    expect(container.textContent).toContain("growth-diary-v1");
    expect(container.textContent).toContain("growth-diary-analysis-v1");
    expect(container.textContent).toContain("detail-only-secret");
    await act(async () => root.unmount());
  });

  it("shows honest legacy provenance and keeps the card on detail failure", async () => {
    const legacy = entry("legacy");
    fetchDetail.mockRejectedValueOnce(new Error("detail unavailable"));
    const container = document.createElement("div");
    const root = createRoot(container);

    await act(async () => root.render(<GrowthDiaryEntryCard entry={legacy} />));
    await act(async () => container.querySelector("button")?.click());

    expect(container.textContent).toContain("AI 來源資訊暫時無法載入");
    expect(container.textContent).toContain("這兩天米糕吃得比較少");

    fetchDetail.mockResolvedValueOnce({
      ...legacy,
      ai_provenance: {
        provenance_status: "legacy_missing",
        provider: null,
        model_name: null,
        model_version: null,
        prompt_version: null,
        output_schema_version: null,
        analyzed_at: null,
      },
      ai_raw_output: null,
    });
    await act(async () => container.querySelector("button")?.click());
    await act(async () => container.querySelector("button")?.click());
    expect(container.textContent).toContain("來源資訊未留存");
    await act(async () => root.unmount());
  });
});
