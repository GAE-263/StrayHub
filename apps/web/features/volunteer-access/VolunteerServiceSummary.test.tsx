// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { VolunteerServiceSummary } from "./VolunteerServiceSummary";

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

function render(props: React.ComponentProps<typeof VolunteerServiceSummary>) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root?.render(<VolunteerServiceSummary {...props} />));
}

const summary = {
  current_shelter_visits: 4,
  total_strayhub_visits: 26,
  visits_last_180_days: 11,
  visits_last_90_days: 6,
  visits_last_30_days: 2,
  last_visit_at: "2026-08-29T08:00:00Z",
  active_months_last_6_months: 5,
  recent_status: "consistently_active" as const,
  has_active_platform_restriction: false,
  approval_blocked: false,
};

describe("VolunteerServiceSummary", () => {
  it("renders aggregate experience without other shelter details", () => {
    render({ summary, loading: false, error: "" });

    expect(container?.textContent).toContain("累積服務26 次");
    expect(container?.textContent).toContain("最近半年11 次");
    expect(container?.textContent).toContain("最近三個月6 次");
    expect(container?.textContent).toContain("持續參與");
    expect(container?.textContent).toContain("沒有需要注意");
    expect(container?.textContent).not.toContain("收容所 B");
    expect(container?.textContent).not.toContain("UUID");
  });

  it("renders a blocking platform restriction without incident details", () => {
    render({
      summary: {
        ...summary,
        has_active_platform_restriction: true,
        approval_blocked: true,
      },
      loading: false,
      error: "",
    });

    expect(container?.textContent).toContain("目前不可直接核准");
    expect(container?.textContent).not.toContain("事件內容");
  });

  it("distinguishes loading and error states", () => {
    render({ summary: null, loading: true, error: "" });
    expect(container?.textContent).toContain("正在計算服務經驗");
    act(() => {
      root?.render(
        <VolunteerServiceSummary
          summary={null}
          loading={false}
          error="服務紀錄失敗"
        />,
      );
    });
    expect(container?.textContent).toContain("服務紀錄失敗");
  });
});
