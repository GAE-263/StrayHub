import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { ProtectedRouteState } from "./ProtectedRouteState";

describe("ProtectedRouteState", () => {
  it.each([
    "checking",
    "redirecting",
    "context-required",
    "temporary-error",
    "re-entry",
    "access-unavailable",
  ] as const)(
    "does not render protected children while state is %s",
    (state) => {
      const html = renderToStaticMarkup(
        <ProtectedRouteState state={state}>
          <span>protected children</span>
        </ProtectedRouteState>,
      );

      expect(html).not.toContain("protected children");
      const expectedRole = [
        "temporary-error",
        "re-entry",
        "access-unavailable",
      ].includes(state)
        ? 'role="alert"'
        : 'role="status"';
      expect(html).toContain(expectedRole);
    },
  );

  it("renders children only after the route is allowed", () => {
    const html = renderToStaticMarkup(
      <ProtectedRouteState state="allowed">
        <span>protected children</span>
      </ProtectedRouteState>,
    );

    expect(html).toContain("protected children");
  });

  it("exposes retry and safe navigation actions for recoverable states", () => {
    const onRetry = vi.fn();
    const onReenter = vi.fn();
    const onBack = vi.fn();
    const html = renderToStaticMarkup(
      <ProtectedRouteState
        state="temporary-error"
        onRetry={onRetry}
        onBack={onBack}
      />,
    );
    const reentry = renderToStaticMarkup(
      <ProtectedRouteState
        state="re-entry"
        onReenter={onReenter}
        onBack={onBack}
      />,
    );

    expect(html).toContain("服務暫時無法使用");
    expect(html).toContain("重試");
    expect(html).toContain("返回");
    expect(reentry).toContain("重新進入志工入口");
    expect(reentry).toContain("重新進入");
    expect(onRetry).not.toHaveBeenCalled();
    expect(onReenter).not.toHaveBeenCalled();
  });

  it("keeps actions outside the live region and exposes context recovery choices", () => {
    const html = renderToStaticMarkup(
      <ProtectedRouteState
        state="context-required"
        onRetry={() => undefined}
        onBack={() => undefined}
        onContactManager={() => undefined}
      />,
    );
    const unavailable = renderToStaticMarkup(
      <ProtectedRouteState
        state="access-unavailable"
        onWaitApproval={() => undefined}
        onReapply={() => undefined}
        onContactManager={() => undefined}
      />,
    );

    expect(html).toContain("聯絡管理者");
    expect(html).toContain('class="ui-button');
    expect(html).toContain('</div><div class="state-action">');
    expect(unavailable).toContain("等待核准");
    expect(unavailable).toContain("重新報名");
    expect(unavailable).toContain("聯絡管理者");
  });

  it("uses an assertive alert only for an unavailable access state", () => {
    const html = renderToStaticMarkup(
      <ProtectedRouteState state="access-unavailable" />,
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain("目前沒有可用的志工權限");
  });
});
