// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VolunteerApplicationStatusPage } from "./VolunteerApplicationStatusPage";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const organizationId = "11111111-1111-4111-8111-111111111111";

function response(items: unknown[], ok = true) {
  return {
    ok,
    json: async () => (ok ? { items } : { code: "dependency_unavailable" }),
  };
}

describe("VolunteerApplicationStatusPage", () => {
  let host: HTMLDivElement;
  let root: Root;
  const startApplication = vi.fn();
  const returnToLine = vi.fn();

  beforeEach(() => {
    host = document.createElement("div");
    document.body.append(host);
    root = createRoot(host);
    startApplication.mockReset();
    returnToLine.mockReset();
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
    vi.restoreAllMocks();
  });

  async function render() {
    await act(async () => {
      root.render(
        <VolunteerApplicationStatusPage
          idToken="line-token"
          focusedOrganizationId={organizationId}
          onStartApplication={startApplication}
          onReturnToLine={returnToLine}
        />,
      );
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  it("keeps an empty status view explicit", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response([])));
    await render();
    expect(host.textContent).toContain("我的志工申請");
    expect(host.textContent).toContain("目前沒有志工申請紀錄");
    [...host.querySelectorAll("button")]
      .find((button) => button.textContent?.includes("前往志工報名"))
      ?.click();
    expect(startApplication).toHaveBeenCalledOnce();
  });

  it("shows pending dates without fabricated grant dates", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response([
          {
            organization: {
              id: organizationId,
              name: "新北市新店區公立動物之家",
              address: "新北市新店區",
            },
            application: {
              id: "application-a",
              status: "pending",
              submitted_at: "2026-08-27T01:00:00Z",
            },
            service_dates: [{ service_date: "2026-09-01", status: "pending" }],
            grant: null,
            effective_status: "pending",
          },
        ]),
      ),
    );
    await render();
    expect(host.textContent).toContain("新北市新店區公立動物之家");
    expect(host.textContent).toContain("審核中");
    expect(host.textContent).toContain("服務日期");
    expect(host.textContent).not.toContain("授權期間");
  });

  it("uses stored grant dates for approved applications", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response([
          {
            organization: {
              id: organizationId,
              name: "毛小孩幸福聯盟協會",
              address: null,
            },
            application: {
              id: "application-b",
              status: "approved",
              submitted_at: "2026-08-20T01:00:00Z",
            },
            service_dates: [{ service_date: "2026-08-28", status: "approved" }],
            grant: {
              status: "active",
              valid_from: "2026-08-28T00:00:00+08:00",
              expires_at: "2026-08-29T00:00:00+08:00",
            },
            effective_status: "active",
          },
        ]),
      ),
    );
    await render();
    expect(host.textContent).toContain("已核准・授權中");
    expect(host.textContent).toContain("授權期間");
  });

  it("does not fall back to signup on an API error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response([], false)));
    await render();
    expect(host.textContent).toContain("我的志工申請");
    expect(host.textContent).toContain("LINE 身分服務暫時無法使用");
    expect(host.textContent).not.toContain("選擇想服務的地區");
  });
});
