// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import VolunteerApplicationClient from "./VolunteerApplicationClient";

const liffMock = vi.hoisted(() => ({
  init: vi.fn(() => Promise.resolve()),
  isLoggedIn: vi.fn(() => true),
  getIDToken: vi.fn(() => "new-line-id-token"),
  login: vi.fn(),
  closeWindow: vi.fn(),
}));

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

let query = "";
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(query),
}));
vi.mock("@line/liff", () => ({
  default: liffMock,
}));

const organizationId = "11111111-1111-4111-8111-111111111111";
const directory = {
  regions: [
    {
      name: "新北市",
      organizations: [
        {
          id: organizationId,
          name: "新北市新店區公立動物之家",
          address: "新北市新店區",
        },
      ],
    },
  ],
};

describe("VolunteerApplicationClient directory", () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    query = "";
    window.sessionStorage.clear();
    window.history.replaceState({}, "", "/volunteer-application");
    liffMock.init.mockReset();
    liffMock.init.mockResolvedValue(undefined);
    liffMock.isLoggedIn.mockReturnValue(true);
    liffMock.getIDToken.mockReturnValue("new-line-id-token");
    host = document.createElement("div");
    document.body.append(host);
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        return Promise.resolve({
          ok: true,
          json: async () =>
            url.includes("self-status")
              ? { items: [] }
              : url.endsWith("/v1/volunteer-applications/status")
                ? {
                    organization: {
                      ...directory.regions[0].organizations[0],
                      applications_enabled: true,
                      insurance_required: false,
                    },
                    application: null,
                    grant: null,
                    effective_status: "none",
                    next_actions: ["apply"],
                  }
                : directory,
        });
      }),
    );
  });

  afterEach(() => {
    host.remove();
    vi.restoreAllMocks();
  });

  it("discovers region then shelter from the backend directory", async () => {
    const root = createRoot(host);
    await act(async () => {
      root.render(<VolunteerApplicationClient liffId="shared-liff" />);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(host.textContent).toContain("選擇想服務的地區");
    expect(host.textContent).not.toContain("新北市新店區公立動物之家");

    await act(async () => {
      [...host.querySelectorAll("button")]
        .find((item) => item.textContent?.includes("新北市"))
        ?.click();
    });
    expect(host.textContent).toContain("新北市新店區公立動物之家");
    expect(host.textContent).toContain("新北市新店區");
    await act(async () => root.unmount());
  });

  it("shows an unavailable state for a tampered organization hint", async () => {
    query = "organization_id=22222222-2222-4222-8222-222222222222";
    const root = createRoot(host);
    await act(async () => {
      root.render(<VolunteerApplicationClient liffId="shared-liff" />);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(host.textContent).toContain("此收容所目前無法報名");
    expect(host.textContent).toContain("重新選擇地區與收容所");
    await act(async () => {
      [...host.querySelectorAll("button")]
        .find((item) => item.textContent?.includes("重新選擇地區"))
        ?.click();
    });
    expect(host.textContent).toContain("選擇想服務的地區");
    await act(async () => root.unmount());
  });

  it("preserves a valid organization preselection in application mode", async () => {
    query = `organization_id=${organizationId}`;
    const root = createRoot(host);
    await act(async () => {
      root.render(<VolunteerApplicationClient liffId="shared-liff" />);
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(host.textContent).toContain("申請成為");
    expect(host.textContent).toContain("新北市新店區公立動物之家");
    expect(host.textContent).not.toContain("選擇想服務的地區");
    await act(async () => root.unmount());
  });

  it("opens organization-scoped status from a pending application without reloading", async () => {
    query = `organization_id=${organizationId}`;
    window.history.replaceState(
      {},
      "",
      `/volunteer-application?organization_id=${organizationId}`,
    );
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        return Promise.resolve({
          ok: true,
          json: async () =>
            url.includes("self-status")
              ? { items: [] }
              : url.endsWith("/v1/volunteer-applications/status")
                ? {
                    organization: {
                      ...directory.regions[0].organizations[0],
                      applications_enabled: true,
                      insurance_required: false,
                    },
                    application: {
                      id: "application-a",
                      status: "pending",
                      version: 1,
                    },
                    grant: null,
                    effective_status: "pending",
                    next_actions: ["wait", "withdraw"],
                  }
                : directory,
        });
      }),
    );
    const root = createRoot(host);
    await act(async () => {
      root.render(<VolunteerApplicationClient liffId="shared-liff" />);
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(host.textContent).toContain("申請已送出");

    await act(async () => {
      [...host.querySelectorAll("button")]
        .find((button) => button.textContent?.includes("查看申請狀態"))
        ?.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(host.textContent).toContain("我的志工申請");
    expect(host.textContent).not.toContain("選擇想服務的地區");
    expect(window.location.search).toBe(
      `?view=status&organization_id=${organizationId}`,
    );
    await act(async () => root.unmount());
  });

  it.each(["view=status", `liff.state=${encodeURIComponent("?view=status")}`])(
    "routes %s directly to the status experience",
    async (value) => {
      query = value;
      const root = createRoot(host);
      await act(async () => {
        root.render(<VolunteerApplicationClient liffId="shared-liff" />);
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });
      expect(host.textContent).toContain("我的志工申請");
      expect(host.textContent).toContain("目前沒有志工申請紀錄");
      expect(host.textContent).not.toContain("選擇想服務的地區");
      await act(async () => root.unmount());
    },
  );

  it("keeps status through a LIFF secondary-redirect remount", async () => {
    let resolveInitialInit: (() => void) | undefined;
    liffMock.init
      .mockImplementationOnce(
        () =>
          new Promise<void>((resolve) => {
            resolveInitialInit = resolve;
          }),
      )
      .mockResolvedValueOnce(undefined);
    query = `liff.state=${encodeURIComponent("?view=status")}`;
    window.history.replaceState({}, "", `/volunteer-application?${query}`);
    const initialRoot = createRoot(host);
    await act(async () => {
      initialRoot.render(<VolunteerApplicationClient liffId="shared-liff" />);
      await Promise.resolve();
    });
    expect(host.textContent).toContain("正在確認 LINE 身分");

    await act(async () => initialRoot.unmount());
    query = "";
    window.history.replaceState({}, "", "/volunteer-application");
    const redirectedRoot = createRoot(host);
    await act(async () => {
      redirectedRoot.render(
        <VolunteerApplicationClient liffId="shared-liff" />,
      );
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(host.textContent).toContain("我的志工申請");
    expect(host.textContent).toContain("目前沒有志工申請紀錄");
    expect(host.textContent).not.toContain("選擇想服務的地區");
    expect(window.location.search).toBe("?view=status");
    resolveInitialInit?.();
    await act(async () => redirectedRoot.unmount());
  });

  it("enters application mode from empty status only after user action", async () => {
    query = "view=status";
    window.history.replaceState({}, "", "/volunteer-application?view=status");
    const root = createRoot(host);
    await act(async () => {
      root.render(<VolunteerApplicationClient liffId="shared-liff" />);
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(host.textContent).toContain("目前沒有志工申請紀錄");
    await act(async () => {
      [...host.querySelectorAll("button")]
        .find((button) => button.textContent?.includes("前往志工報名"))
        ?.click();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(host.textContent).toContain("選擇想服務的地區");
    expect(window.location.search).toBe("");
    await act(async () => root.unmount());
  });

  it("logs lifecycle metadata without identity tokens or raw LIFF state", async () => {
    const debug = vi
      .spyOn(console, "debug")
      .mockImplementation(() => undefined);
    query = `liff.state=${encodeURIComponent("?view=status")}`;
    const root = createRoot(host);
    await act(async () => {
      root.render(<VolunteerApplicationClient liffId="shared-liff" />);
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    const output = JSON.stringify(debug.mock.calls);
    expect(output).toContain("[volunteer-liff] parsed-intent");
    expect(output).toContain("[volunteer-liff] status-fetch:success");
    expect(output).not.toContain("new-line-id-token");
    expect(output).not.toContain("?view=status");
    await act(async () => root.unmount());
  });
});
