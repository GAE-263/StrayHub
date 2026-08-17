import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PermissionDeniedState,
  SavingState,
} from "./StateViews";

describe("StateViews", () => {
  it("distinguishes loading, saving, empty and permission states", () => {
    const html = renderToStaticMarkup(
      <>
        <LoadingState title="載入中" />
        <SavingState title="儲存中" />
        <EmptyState title="沒有資料" />
        <PermissionDeniedState description="請聯絡管理者" />
      </>,
    );

    expect(html).toContain('role="status"');
    expect(html).toContain("載入中");
    expect(html).toContain("儲存中");
    expect(html).toContain("沒有資料");
    expect(html).toContain("沒有查看權限");
  });

  it("keeps errors assertive and exposes a retry action", () => {
    const html = renderToStaticMarkup(
      <ErrorState
        title="無法載入"
        description="請稍後再試"
        action={<button type="button">重試</button>}
      />,
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain('aria-live="assertive"');
    expect(html).toContain("請稍後再試");
    expect(html).toContain("重試");
  });
});
