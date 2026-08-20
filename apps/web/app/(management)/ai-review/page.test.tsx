// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import AiReviewPage from "./page";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

if (!HTMLDialogElement.prototype.showModal) {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value() {
      this.open = true;
    },
  });
}

if (!HTMLDialogElement.prototype.close) {
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value() {
      this.open = false;
    },
  });
}

const observation = {
  id: "observation-1",
  source_type: "line",
  source_id: "report-1",
  status: "succeeded",
  failure_reason: null,
  raw_ai_output: { label: "possible injury" },
  validated_ai_observation: { label: "possible injury" },
  human_review_result: null,
};

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

let root: Root | undefined;
let container: HTMLDivElement | undefined;
let fetchMock: ReturnType<typeof vi.fn>;

async function renderPage() {
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.includes("/review"))
      return response({ ...observation, status: "rejected" });
    return response({ items: [observation] });
  });
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("prompt", vi.fn());
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(<AiReviewPage />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  container?.remove();
  container = undefined;
  vi.unstubAllGlobals();
});

describe("AI review queue", () => {
  it("uses a governed dialog instead of window.prompt for rejection", async () => {
    await renderPage();
    expect(container?.querySelector("h1")?.textContent).toBe("AI 人工覆核");
    expect(container?.textContent).not.toContain("AI Queue");
    const rejectButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "拒絕");

    await act(async () => rejectButton?.click());

    expect(container?.textContent).toContain("拒絕 AI Observation");
    expect(container?.querySelector("textarea")).not.toBeNull();
    expect(container?.textContent).toContain("拒絕會保留原始 AI 輸出");
    expect(window.prompt).not.toHaveBeenCalled();

    const textarea = container?.querySelector("textarea");
    await act(async () => {
      if (textarea) {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype,
          "value",
        )?.set;
        setter?.call(textarea, "標記為不適用");
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
        textarea.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    const confirmButton = Array.from(
      container?.querySelectorAll("button") ?? [],
    ).find((button) => button.textContent?.trim() === "確認拒絕");
    await act(async () => confirmButton?.click());

    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/management/ai-review/observation-1/review",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
