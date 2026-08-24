// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { ApplicationBatchWorkbench } from "./ApplicationBatchWorkbench";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

describe("ApplicationBatchWorkbench", () => {
  it("keeps all-filtered snapshot count and partial results visible", () => {
    const html = renderToStaticMarkup(
      <ApplicationBatchWorkbench
        applications={Array.from({ length: 100 }, (_, index) => ({
          id: `app-${index}`,
          display_name: `志工 ${index}`,
          status: "pending",
          version: 1,
        }))}
        matchingCount={1200}
        filter={{ status: "pending", unassigned: true }}
        onViewApplicant={() => undefined}
      />,
    );
    expect(html).toContain("目前篩選結果全部 1,200 筆");
    expect(html).toContain("共同授權期限");
    expect(html).toContain("逐筆結果");
    expect(html).toContain("ui-checkbox");
    expect(html).toContain("ui-input");
    expect(html).toContain("ui-table batch-table");
    expect(html).toContain("ui-button ui-button-default");
    expect(html).toContain("查看申請人");
    expect(html).not.toContain("bg-emerald");
  });

  it("uses application ids as stable keys for batch results", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    const onSubmit = vi.fn().mockResolvedValue({
      id: "batch-a",
      status: "queued",
      requested_count: 2,
      processed_count: 0,
      succeeded_count: 0,
      conflict_count: 0,
      failed_count: 0,
    });
    const onLoadItems = vi.fn().mockResolvedValue([
      {
        application_id: "app-a",
        expected_version: 1,
        result: "succeeded",
      },
      {
        application_id: "app-b",
        expected_version: 1,
        result: "failed",
      },
    ]);
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => {});
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function close() {
      this.open = false;
    };

    await act(async () => {
      root.render(
        <ApplicationBatchWorkbench
          applications={[
            {
              id: "app-a",
              display_name: "志工 A",
              status: "pending",
              version: 1,
            },
          ]}
          matchingCount={1}
          filter={{ status: "pending", unassigned: true }}
          onSubmit={onSubmit}
          onLoadItems={onLoadItems}
        />,
      );
    });
    const allFiltered = container.querySelector<HTMLInputElement>(
      'input[type="checkbox"]',
    );
    await act(async () => allFiltered?.click());
    await act(async () =>
      Array.from(container.querySelectorAll("button"))
        .find((button) => button.textContent?.includes("確認並建立批次"))
        ?.click(),
    );
    await act(async () =>
      Array.from(container.querySelectorAll("button"))
        .find((button) => button.textContent?.includes("送出完整快照"))
        ?.click(),
    );

    expect(container.textContent).toContain("app-a");
    expect(container.textContent).toContain("app-b");
    expect(
      consoleError.mock.calls.some((args) =>
        args.some((argument) =>
          String(argument).includes(
            "Each child in a list should have a unique",
          ),
        ),
      ),
    ).toBe(false);

    await act(async () =>
      Array.from(container.querySelectorAll("button"))
        .find((button) => button.textContent?.includes("重試失敗"))
        ?.click(),
    );
    expect(onSubmit).toHaveBeenLastCalledWith(
      expect.objectContaining({
        selection: expect.objectContaining({
          mode: "explicit_items",
          service_date: null,
          items: [
            {
              application_id: "app-b",
              expected_version: 1,
            },
          ],
        }),
      }),
    );
    consoleError.mockRestore();
    await act(async () => root.unmount());
  });

  it("notifies page when a batch reaches a terminal success status", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    const onBatchTerminalSuccess = vi.fn();
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function close() {
      this.open = false;
    };

    await act(async () => {
      root.render(
        <ApplicationBatchWorkbench
          applications={[
            {
              id: "app-a",
              display_name: "志工 A",
              status: "pending",
              version: 1,
            },
          ]}
          matchingCount={1}
          filter={{ status: "pending", service_date: "2026-08-25" }}
          onSubmit={vi.fn().mockResolvedValue({
            id: "batch-a",
            status: "queued",
            requested_count: 1,
            processed_count: 0,
            succeeded_count: 0,
            conflict_count: 0,
            failed_count: 0,
          })}
          onLoadItems={vi.fn().mockResolvedValue([])}
          onLoadBatch={vi.fn().mockResolvedValue({
            id: "batch-a",
            status: "completed",
            requested_count: 1,
            processed_count: 1,
            succeeded_count: 1,
            conflict_count: 0,
            failed_count: 0,
          })}
          onBatchTerminalSuccess={onBatchTerminalSuccess}
        />,
      );
    });
    await act(async () =>
      (
        container.querySelector('input[type="checkbox"]') as HTMLInputElement
      )?.click(),
    );
    await act(async () =>
      Array.from(container.querySelectorAll("button"))
        .find((button) => button.textContent?.includes("確認並建立批次"))
        ?.click(),
    );
    await act(async () =>
      Array.from(container.querySelectorAll("button"))
        .find((button) => button.textContent?.includes("送出完整快照"))
        ?.click(),
    );
    await act(async () =>
      Array.from(container.querySelectorAll("button"))
        .find((button) => button.textContent?.includes("更新進度"))
        ?.click(),
    );

    expect(onBatchTerminalSuccess).toHaveBeenCalledWith(
      expect.objectContaining({ id: "batch-a", status: "completed" }),
    );
    await act(async () => root.unmount());
  });
});
