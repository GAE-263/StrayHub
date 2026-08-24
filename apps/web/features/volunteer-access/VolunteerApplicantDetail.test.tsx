// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VolunteerApplicantDetail } from "./VolunteerApplicantDetail";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

let root: Root | undefined;
let container: HTMLDivElement | undefined;

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  container?.remove();
  container = undefined;
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
});

async function renderDetail(onClose = vi.fn()) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(
      <VolunteerApplicantDetail
        organizationId="org-a"
        applicationId="application-a"
        open
        onClose={onClose}
      />,
    );
  });
  return onClose;
}

describe("VolunteerApplicantDetail", () => {
  it("loads masked detail first and only reveals after explicit action", async () => {
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function close() {
      this.open = false;
    };
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input).endsWith("/pii-reveal")) {
          expect(init?.method).toBe("POST");
          expect(JSON.parse(String(init?.body))).toEqual({
            purpose_code: "application_review",
          });
          return response({
            applicant_name: "核准顯示名",
            phone_number: "0900000000",
            basic_profile: { experience: "synthetic" },
          });
        }
        return response({
          id: "application-a",
          organization_id: "org-a",
          display_name: "LINE 志工",
          status: "pending",
          submitted_at: "2026-08-24T00:00:00Z",
          decided_at: null,
          decision_reason: null,
          version: 1,
          service_dates: [],
        });
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    window.sessionStorage.setItem("access_token", "synthetic-token");

    await renderDetail();
    await act(async () => flush());

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).not.toContain("pii-reveal");
    expect(container?.textContent).toContain("LINE 志工");
    expect(container?.textContent).not.toContain("核准顯示名");

    await act(async () => {
      Array.from(container?.querySelectorAll("button") ?? [])
        .find((button) => button.textContent?.includes("申請審核用途揭露"))
        ?.click();
      await flush();
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(container?.textContent).toContain("核准顯示名");
    expect(container?.textContent).toContain("0900000000");
  });

  it("keeps reveal failure free of plaintext and clears revealed state on close", async () => {
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function close() {
      this.open = false;
    };
    const onClose = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).endsWith("/pii-reveal")
          ? response({ code: "pii_audit_unavailable" }, 503)
          : response({
              id: "application-a",
              organization_id: "org-a",
              display_name: "LINE 志工",
              status: "pending",
              submitted_at: "2026-08-24T00:00:00Z",
              decided_at: null,
              decision_reason: null,
              version: 1,
              service_dates: [],
            }),
      ),
    );

    await renderDetail(onClose);
    await act(async () => flush());
    await act(async () => {
      Array.from(container?.querySelectorAll("button") ?? [])
        .find((button) => button.textContent?.includes("申請審核用途揭露"))
        ?.click();
      await flush();
    });

    expect(container?.textContent).toContain("目前無法揭露申請人資料");
    expect(container?.textContent).not.toContain("核准顯示名");
    expect(container?.textContent).not.toContain("0900000000");

    await act(async () => {
      container
        ?.querySelector<HTMLButtonElement>(
          'button[aria-label="關閉申請人資料"]',
        )
        ?.click();
    });
    expect(onClose).toHaveBeenCalledOnce();
    expect(container?.textContent).not.toContain("核准顯示名");
    expect(container?.textContent).not.toContain("0900000000");
  });
});
