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

  it("animates only transient states and uses semantic static icons otherwise", () => {
    const loading = renderToStaticMarkup(<LoadingState title="載入中" />);
    const saving = renderToStaticMarkup(<SavingState title="儲存中" />);
    const empty = renderToStaticMarkup(<EmptyState title="沒有資料" />);
    const error = renderToStaticMarkup(<ErrorState title="載入失敗" />);
    const permission = renderToStaticMarkup(<PermissionDeniedState />);

    expect(loading).toContain("loading-dot");
    expect(saving).toContain("loading-dot");

    expect(empty).not.toContain("loading-dot");
    expect(empty).toContain('data-state-icon="empty"');
    expect(empty).toContain("lucide-inbox");

    expect(error).not.toContain("loading-dot");
    expect(error).toContain('data-state-icon="error"');
    expect(error).toContain("lucide-triangle-alert");

    expect(permission).not.toContain("loading-dot");
    expect(permission).toContain('data-state-icon="permission-denied"');
    expect(permission).toContain("lucide-shield-alert");
  });
});
