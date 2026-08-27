// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import VolunteerApplicationClient from "./VolunteerApplicationClient";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

let query = "";
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(query),
}));
vi.mock("@line/liff", () => ({
  default: {
    init: vi.fn(() => Promise.resolve()),
    isLoggedIn: vi.fn(() => true),
    getIDToken: vi.fn(() => "new-line-id-token"),
    login: vi.fn(),
    closeWindow: vi.fn(),
  },
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
    host = document.createElement("div");
    document.body.append(host);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => directory }),
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
});
