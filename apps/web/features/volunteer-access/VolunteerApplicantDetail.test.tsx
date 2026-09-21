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

function summaryResponse(overrides: Record<string, unknown> = {}) {
  return response({
    current_shelter_visits: 2,
    total_strayhub_visits: 6,
    visits_last_180_days: 5,
    visits_last_90_days: 3,
    visits_last_30_days: 1,
    last_visit_at: "2026-08-20T00:00:00Z",
    active_months_last_6_months: 3,
    recent_status: "recently_active",
    has_active_platform_restriction: false,
    approval_blocked: false,
    ...overrides,
  });
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
  it("opens applicant detail and automatically requests application-review PII", async () => {
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function close() {
      this.open = false;
    };
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input).includes("service-summary")) return summaryResponse();
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

    expect(fetchMock).toHaveBeenCalledTimes(3);
    const revealCall = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith("/pii-reveal"),
    );
    expect(revealCall).toBeDefined();
    expect(revealCall?.[1]).toEqual(
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ purpose_code: "application_review" }),
      }),
    );
    expect(container?.textContent).toContain("LINE 志工");
    expect(container?.textContent).toContain("核准顯示名");
    expect(container?.textContent).toContain("0900000000");
    expect(container?.textContent).toContain(
      "申請人資料僅供本次審核使用，查看紀錄將留存。",
    );
    expect(container?.textContent).not.toContain("申請審核用途揭露");
    expect(window.localStorage.getItem("applicant_name")).toBeNull();
    expect(window.sessionStorage.getItem("applicant_name")).toBeNull();
  });

  it("keeps masked detail visible when automatic reveal fails", async () => {
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
        String(input).includes("service-summary")
          ? summaryResponse()
          : String(input).endsWith("/pii-reveal")
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

    expect(container?.textContent).toContain("LINE 志工");
    expect(container?.textContent).toContain(
      "目前無法查看申請人資料，請稍後再試。",
    );
    expect(container?.textContent).not.toContain("核准顯示名");
    expect(container?.textContent).not.toContain("0900000000");
  });

  it("clears automatically revealed data on close", async () => {
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
        String(input).includes("service-summary")
          ? summaryResponse()
          : String(input).endsWith("/pii-reveal")
            ? response({
                applicant_name: "核准顯示名",
                phone_number: "0900000000",
                basic_profile: null,
              })
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
    expect(container?.textContent).toContain("核准顯示名");

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

  it("rejects a stale reveal response after switching applicants", async () => {
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function close() {
      this.open = false;
    };
    let resolveAReveal: ((value: Response) => void) | undefined;
    const delayedAReveal = new Promise<Response>((resolve) => {
      resolveAReveal = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("service-summary")) return summaryResponse();
        if (url.endsWith("application-a/pii-reveal")) return delayedAReveal;
        if (url.endsWith("application-b/pii-reveal")) {
          return response({
            applicant_name: "申請人 B",
            phone_number: "0922222222",
            basic_profile: null,
          });
        }
        return response({
          id: url.endsWith("application-b") ? "application-b" : "application-a",
          organization_id: "org-a",
          display_name: url.endsWith("application-b")
            ? "LINE 志工 B"
            : "LINE 志工 A",
          status: "pending",
          submitted_at: "2026-08-24T00:00:00Z",
          decided_at: null,
          decision_reason: null,
          version: 1,
          service_dates: [],
        });
      }),
    );

    await renderDetail();
    await act(async () => flush());
    await act(async () => {
      root?.render(
        <VolunteerApplicantDetail
          organizationId="org-a"
          applicationId="application-b"
          open
          onClose={vi.fn()}
        />,
      );
      await flush();
    });
    resolveAReveal?.(
      response({
        applicant_name: "申請人 A",
        phone_number: "0911111111",
        basic_profile: null,
      }),
    );
    await act(async () => flush());

    expect(container?.textContent).toContain("申請人 B");
    expect(container?.textContent).not.toContain("申請人 A");
    expect(container?.textContent).not.toContain("0911111111");
  });

  it("automatically loads aggregate summary and clears it on close", async () => {
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function close() {
      this.open = false;
    };
    const onClose = vi.fn();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("service-summary")) {
        expect(url).toContain("purpose_code=volunteer_service_history_review");
        return summaryResponse({ total_strayhub_visits: 12 });
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
    });
    vi.stubGlobal("fetch", fetchMock);

    await renderDetail(onClose);
    await act(async () => flush());
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(container?.textContent).not.toContain("收容所 B");
    expect(container?.textContent).toContain("累積服務12 次");

    await act(async () => {
      container
        ?.querySelector<HTMLButtonElement>(
          'button[aria-label="關閉申請人資料"]',
        )
        ?.click();
    });
    expect(onClose).toHaveBeenCalledOnce();
    expect(container?.textContent).not.toContain("累積服務12 次");
  });

  it("rejects a stale summary response after switching applicants", async () => {
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function close() {
      this.open = false;
    };
    let resolveSummary: ((value: Response) => void) | undefined;
    const delayedSummary = new Promise<Response>((resolve) => {
      resolveSummary = resolve;
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes("application-a/service-summary"))
        return delayedSummary;
      if (String(input).includes("service-summary")) return summaryResponse();
      return response({
        id: String(input).includes("application-b")
          ? "application-b"
          : "application-a",
        organization_id: "org-a",
        display_name: "LINE 志工",
        status: "pending",
        submitted_at: "2026-08-24T00:00:00Z",
        decided_at: null,
        decision_reason: null,
        version: 1,
        service_dates: [],
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    await renderDetail();
    await act(async () => flush());

    await act(async () => {
      root?.render(
        <VolunteerApplicantDetail
          organizationId="org-a"
          applicationId="application-b"
          open
          onClose={vi.fn()}
        />,
      );
      await flush();
    });
    resolveSummary?.(summaryResponse({ total_strayhub_visits: 99 }));
    await act(async () => flush());
    expect(container?.textContent).not.toContain("累積服務99 次");
  });

  it("attaches the platform support reason header to the detail request when reviewing as PLATFORM_ADMIN", async () => {
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function close() {
      this.open = false;
    };
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        response({
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
    );
    vi.stubGlobal("fetch", fetchMock);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(
        <VolunteerApplicantDetail
          organizationId="org-a"
          applicationId="application-a"
          open
          onClose={vi.fn()}
          platformSupportReason="平台支援：協助收容所審核積壓申請"
        />,
      );
    });
    await act(async () => flush());

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0];
    const headers = new Headers((init as RequestInit | undefined)?.headers);
    expect(headers.get("X-Platform-Support-Reason")).toBe(
      encodeURIComponent("平台支援：協助收容所審核積壓申請"),
    );
  });

  it("skips PII reveal and service-summary requests for PLATFORM_ADMIN and shows a fallback note", async () => {
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function close() {
      this.open = false;
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (
        String(input).includes("service-summary") ||
        String(input).endsWith("/pii-reveal")
      ) {
        throw new Error(
          `should not call platform-restricted endpoint: ${String(input)}`,
        );
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
    });
    vi.stubGlobal("fetch", fetchMock);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(
        <VolunteerApplicantDetail
          organizationId="org-a"
          applicationId="application-a"
          open
          onClose={vi.fn()}
          platformSupportReason="平台支援：協助收容所審核積壓申請"
        />,
      );
    });
    await act(async () => flush());

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(container?.textContent).toContain("LINE 志工");
    expect(container?.textContent).toContain(
      "姓名、電話等個資與跨收容所服務紀錄僅收容所管理員可查看",
    );
    expect(container?.textContent).not.toContain("申請人資料僅供本次審核使用");
  });
});
