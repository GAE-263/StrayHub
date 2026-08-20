// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import VolunteerAccessSettingsPage from "./page";

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

describe("volunteer access policy platform support", () => {
  it("does not load tenant policy before a platform admin supplies a support reason", async () => {
    window.sessionStorage.setItem(
      "active_organization_id",
      "567688df-15dc-45a7-aa1d-918f51eec62b",
    );
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path.endsWith("/v1/auth/me")) {
          return response({
            user: {
              id: "platform-admin-a",
              platform_role: "PLATFORM_ADMIN",
              status: "active",
            },
            memberships: [],
          });
        }
        if (path.endsWith("/volunteer-access-policy")) {
          return response({
            organization_id: "567688df-15dc-45a7-aa1d-918f51eec62b",
            applications_enabled: true,
            default_grant_duration_hours: 168,
            version: 1,
          });
        }
        return response({}, 404);
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("React", React);

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(<VolunteerAccessSettingsPage />);
      await flush();
    });

    expect(container.textContent).toContain("平台支援原因");
    expect(
      fetchMock.mock.calls.filter(([input]) =>
        String(input).endsWith("/volunteer-access-policy"),
      ),
    ).toHaveLength(0);
  });
});
