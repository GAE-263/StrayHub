// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { AnimalTimeline } from "../features/animal-timeline/AnimalTimeline";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | undefined;
let container: HTMLDivElement | undefined;

afterEach(async () => {
  await act(async () => {
    root?.unmount();
  });
  root = undefined;
  container?.remove();
  container = undefined;
});

async function renderTimeline(
  props: React.ComponentProps<typeof AnimalTimeline>,
) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(<AnimalTimeline {...props} />);
  });
}

describe("AnimalTimeline", () => {
  it("renders daily summaries, explicit no-report and same-day report count", async () => {
    await renderTimeline({
      days: [
        { date: "2026-08-08", hasReport: false, reportCount: 0 },
        { date: "2026-08-07", hasReport: true, reportCount: 2, reports: [] },
      ],
    });

    expect(container?.textContent).toContain("2026-08-08");
    expect(container?.textContent).toContain("當日沒有事件");
    expect(container?.textContent).toContain("有回報：2 筆");
  });

  it("expands raw note, photo count, AI and human status content", async () => {
    await renderTimeline({
      days: [
        {
          date: "2026-08-07",
          hasReport: true,
          reportCount: 1,
          reports: [
            {
              id: "report-1",
              submittedAt: "2026-08-07T09:00:00+08:00",
              volunteerUserId: "staff-1",
              note: "原始心得",
              observations: {
                urination: "urination.not_observed",
                emotion: "emotion.uncertain",
              },
              observationSnapshots: {
                urination: {
                  code: "urination.not_observed",
                  displayName: "未觀察",
                },
                emotion: {
                  code: "emotion.uncertain",
                  displayName: "無法判斷",
                },
              },
              mediaIds: ["media-1", "media-2"],
              aiJobStatus: "pending",
              status: "saved",
            },
          ],
        },
      ],
    });

    const button = container?.querySelector("button");
    expect(button?.getAttribute("aria-expanded")).toBe("false");
    await act(async () => {
      (button as HTMLButtonElement).click();
    });

    expect(button?.getAttribute("aria-expanded")).toBe("true");
    expect(container?.textContent).toContain("原始心得");
    expect(container?.textContent).toContain("排尿");
    expect(container?.textContent).toContain("未觀察");
    expect(container?.textContent).toContain("情緒");
    expect(container?.textContent).toContain("無法判斷");
    expect(container?.textContent).toContain("照片：2 張");
    expect(container?.textContent).toContain("AI 處理：等待處理（pending）");
    expect(container?.textContent).toContain("人工資料狀態：已保存（saved）");
  });

  it("keeps loading, empty and error states distinguishable", async () => {
    await renderTimeline({ days: [], loading: true });
    expect(container?.querySelector('[role="status"]')?.textContent).toContain(
      "正在載入",
    );

    await act(async () => {
      root?.render(<AnimalTimeline days={[]} />);
    });
    expect(container?.textContent).toContain("目前沒有可顯示的歷程");

    await act(async () => {
      root?.render(<AnimalTimeline days={[]} error="403" />);
    });
    expect(container?.querySelector('[role="alert"]')?.textContent).toContain(
      "403",
    );
  });
});
