// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VolunteerReviewCalendar } from "./VolunteerReviewCalendar";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | undefined;
let container: HTMLDivElement | undefined;

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  container?.remove();
  container = undefined;
});

function render(props: React.ComponentProps<typeof VolunteerReviewCalendar>) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root?.render(<VolunteerReviewCalendar {...props} />));
}

describe("VolunteerReviewCalendar", () => {
  it("renders dates, counts, selected state, and keyboard-accessible buttons", () => {
    render({
      dates: [
        { service_date: "2026-08-25", pending_count: 3 },
        { service_date: "2026-08-26", pending_count: 1 },
      ],
      selectedDate: "2026-08-25",
      onSelectDate: vi.fn(),
    });

    const buttons = container?.querySelectorAll("button") ?? [];
    expect(buttons).toHaveLength(2);
    expect(buttons[0].getAttribute("aria-pressed")).toBe("true");
    expect(buttons[1].getAttribute("aria-pressed")).toBe("false");
    expect(container?.textContent).toContain("3 筆待審核");
    expect(buttons[1].getAttribute("aria-label")).toContain("2026-08-26");
  });

  it("selects a date without owning any decision action", () => {
    const onSelectDate = vi.fn();
    render({
      dates: [{ service_date: "2026-08-25", pending_count: 2 }],
      selectedDate: "",
      onSelectDate,
    });

    act(() => {
      container?.querySelector("button")?.click();
    });
    expect(onSelectDate).toHaveBeenCalledWith("2026-08-25");
  });

  it("distinguishes loading, error, and empty states", () => {
    render({
      dates: [],
      selectedDate: "",
      loading: true,
      onSelectDate: vi.fn(),
    });
    expect(container?.textContent).toContain("載入審核日期中");

    act(() => {
      root?.render(
        <VolunteerReviewCalendar
          dates={[]}
          selectedDate=""
          error="日期載入失敗"
          onSelectDate={vi.fn()}
        />,
      );
    });
    expect(container?.textContent).toContain("日期載入失敗");

    act(() => {
      root?.render(
        <VolunteerReviewCalendar
          dates={[]}
          selectedDate=""
          onSelectDate={vi.fn()}
        />,
      );
    });
    expect(container?.textContent).toContain("目前沒有待審核");
  });
});
