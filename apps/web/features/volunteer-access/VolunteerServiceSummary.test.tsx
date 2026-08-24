// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

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

const item = {
  organization_id: "org-b",
  organization_name: "收容所 B",
  service_date: "2026-05-20",
  service_status: "recorded" as const,
  record_count: 2,
  source: "care_report" as const,
};

describe("VolunteerServiceSummary", () => {
  it("keeps the summary secondary and renders safe provenance fields", () => {
    const onLoad = vi.fn();
    render({
      loaded: false,
      items: [],
      nextCursor: null,
      loading: false,
      error: "",
      onLoad,
      onLoadMore: vi.fn(),
    });
    expect(container?.textContent).not.toContain("收容所 B");

    act(() => {
      container?.querySelector("button")?.click();
    });
    expect(onLoad).toHaveBeenCalledOnce();

    act(() => {
      root?.render(
        <VolunteerServiceSummary
          loaded
          items={[item]}
          nextCursor="cursor"
          loading={false}
          error=""
          onLoad={onLoad}
          onLoadMore={vi.fn()}
        />,
      );
    });
    expect(container?.textContent).toContain("收容所 B");
    expect(container?.textContent).toContain("2026-05-20");
    expect(container?.textContent).toContain("2 筆紀錄");
    expect(container?.textContent).toContain("來源：照護回報");
    expect(container?.textContent).not.toContain("姓名");
    expect(container?.textContent).not.toContain("電話");
  });

  it("distinguishes empty, loading, and error states", () => {
    render({
      loaded: true,
      items: [],
      nextCursor: null,
      loading: false,
      error: "",
      onLoad: vi.fn(),
      onLoadMore: vi.fn(),
    });
    expect(container?.textContent).toContain("目前沒有可顯示");

    act(() => {
      root?.render(
        <VolunteerServiceSummary
          loaded
          items={[]}
          nextCursor={null}
          loading={false}
          error="服務紀錄失敗"
          onLoad={vi.fn()}
          onLoadMore={vi.fn()}
        />,
      );
    });
    expect(container?.textContent).toContain("服務紀錄失敗");
    expect(container?.textContent).not.toContain("目前沒有可顯示");
    expect(container?.textContent).toContain("重試服務紀錄");
  });
});
