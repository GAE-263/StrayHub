import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PermissionDeniedState,
  SavingState,
} from "../components/management/StateViews";
import { describe, expect, it } from "vitest";

describe("P0 UI state matrix", () => {
  it("keeps route state categories distinct and actionable", () => {
    const states = (
      <>
        <LoadingState title="載入中" />
        <SavingState title="儲存中" />
        <EmptyState
          title="目前沒有資料"
          action={<button type="button">調整篩選</button>}
        />
        <ErrorState title="載入失敗" description="保留目前輸入，請重試。" />
        <PermissionDeniedState description="請切換到已授權收容所。" />
      </>
    );
    const html = renderToStaticMarkup(states);
    expect(html).toContain("載入中");
    expect(html).toContain("儲存中");
    expect(html).toContain("調整篩選");
    expect(html).toContain("保留目前輸入");
    expect(html).toContain("切換到已授權收容所");
    expect(html.match(/class="state-card/g)?.length).toBe(5);
  });
});
