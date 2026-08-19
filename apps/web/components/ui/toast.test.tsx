// @vitest-environment jsdom

import React from "react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Toast } from "./toast";

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
  vi.useRealTimers();
});

async function renderToast(element: React.ReactNode) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root?.render(element));
}

describe("Toast", () => {
  it("uses status semantics and the bottom-left styling hook", () => {
    const html = renderToStaticMarkup(
      <Toast>已完成權限調整：本機工作人員 A</Toast>,
    );

    expect(html).toContain('class="ui-toast"');
    expect(html).toContain('role="status"');
    expect(html).toContain('aria-live="polite"');
    expect(html).toContain("已完成權限調整：本機工作人員 A");
    expect(html).not.toContain("bafda56b-f781-48dc-bcd4-e02dc10573d9");
  });

  it("dismisses automatically after the configured timeout", async () => {
    vi.useFakeTimers();
    const onClose = vi.fn();
    await renderToast(
      <Toast duration={5000} onClose={onClose}>
        已完成權限調整
      </Toast>,
    );

    expect(container?.textContent).toContain("已完成權限調整");
    await act(async () => vi.advanceTimersByTime(5000));

    expect(container?.textContent).not.toContain("已完成權限調整");
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("supports manual close without moving focus on mount", async () => {
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.focus();
    const onClose = vi.fn();
    await renderToast(<Toast onClose={onClose}>帳號已建立</Toast>);

    expect(document.activeElement).toBe(trigger);
    const closeButton = container?.querySelector<HTMLButtonElement>(
      'button[aria-label="關閉通知"]',
    );
    await act(async () => closeButton?.click());

    expect(container?.textContent).not.toContain("帳號已建立");
    expect(onClose).toHaveBeenCalledOnce();
    trigger.remove();
  });

  it("restarts the lifecycle when a consecutive message key changes", async () => {
    vi.useFakeTimers();
    await renderToast(
      <Toast duration={5000} messageKey={1}>
        已完成權限調整
      </Toast>,
    );
    await act(async () => vi.advanceTimersByTime(4000));
    await act(async () =>
      root?.render(
        <Toast duration={5000} messageKey={2}>
          已完成權限調整
        </Toast>,
      ),
    );
    await act(async () => vi.advanceTimersByTime(1000));

    expect(container?.textContent).toContain("已完成權限調整");
    await act(async () => vi.advanceTimersByTime(4000));
    expect(container?.textContent).not.toContain("已完成權限調整");
  });
});
