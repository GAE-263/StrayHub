// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CurrentUser, SessionSource } from "../../lib/auth";
import {
  AuthenticatedRouteBoundary,
  type BoundaryLoadResult,
} from "./AuthenticatedRouteBoundary";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

const profile: CurrentUser = {
  user: { id: "user-a", status: "active", platform_role: null },
  memberships: [
    {
      id: "membership-a",
      organization_id: "org-a",
      role: "VOLUNTEER",
      status: "active",
      valid_from: new Date(Date.now() - 60_000).toISOString(),
      expires_at: new Date(Date.now() + 60 * 60_000).toISOString(),
      access_grant: {
        membership_id: "membership-a",
        organization_id: "org-a",
        status: "active",
        valid_from: new Date(Date.now() - 60_000).toISOString(),
        expires_at: new Date(Date.now() + 60 * 60_000).toISOString(),
      },
    },
  ],
};

function result(source: SessionSource = "liff"): BoundaryLoadResult {
  return {
    profile,
    context: { organization_id: "org-a", session_id: "session-a" },
    sessionSource: source,
  };
}

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  window.sessionStorage.clear();
});

afterEach(async () => {
  await act(async () => {
    root.unmount();
  });
  container.remove();
});

describe("AuthenticatedRouteBoundary", () => {
  it("does not mount children before profile and context are allowed", async () => {
    let resolveLoad!: (value: BoundaryLoadResult) => void;
    const loadContext = vi.fn(
      () =>
        new Promise<BoundaryLoadResult>((resolve) => (resolveLoad = resolve)),
    );

    await act(async () => {
      root.render(
        <AuthenticatedRouteBoundary
          area="volunteer"
          pathname="/animal-confirmation"
          loadContext={loadContext}
        >
          <span>protected animal data</span>
        </AuthenticatedRouteBoundary>,
      );
    });

    expect(container.textContent).not.toContain("protected animal data");
    expect(container.textContent).toContain("確認登入狀態");

    await act(async () => resolveLoad(result()));
    expect(container.textContent).toContain("protected animal data");
  });

  it("allows a management role only with a matching active context", async () => {
    const managementProfile: CurrentUser = {
      ...profile,
      memberships: [
        { ...profile.memberships[0], role: "STAFF", access_grant: null },
      ],
    };
    const loadContext = vi.fn(async () => ({
      ...result("local"),
      profile: managementProfile,
    }));

    await act(async () => {
      root.render(
        <AuthenticatedRouteBoundary
          area="management"
          pathname="/"
          loadContext={loadContext}
        >
          <span>management dashboard</span>
        </AuthenticatedRouteBoundary>,
      );
    });

    expect(container.textContent).toContain("management dashboard");
  });

  it("redirects a local session to login without mounting children", async () => {
    const onRedirect = vi.fn();
    const loadContext = vi.fn(async () => {
      throw new Response("unauthorized", { status: 401 });
    });

    await act(async () => {
      root.render(
        <AuthenticatedRouteBoundary
          area="management"
          pathname="/"
          loadContext={loadContext}
          sessionSource="local"
          onRedirect={onRedirect}
        >
          <span>management dashboard</span>
        </AuthenticatedRouteBoundary>,
      );
    });

    expect(container.textContent).not.toContain("management dashboard");
    expect(onRedirect).toHaveBeenCalledWith("/login");
  });

  it("requires context before mounting a management role", async () => {
    const loadContext = vi.fn(async () => ({
      ...result("local"),
      context: { organization_id: "", session_id: "session-a" },
      profile: {
        ...profile,
        memberships: [
          { ...profile.memberships[0], role: "STAFF", access_grant: null },
        ],
      },
    }));

    await act(async () => {
      root.render(
        <AuthenticatedRouteBoundary
          area="management"
          pathname="/"
          loadContext={loadContext}
        >
          <span>management dashboard</span>
        </AuthenticatedRouteBoundary>,
      );
    });

    expect(container.textContent).not.toContain("management dashboard");
    expect(container.textContent).toContain("需要確認目前收容所");
  });

  it("shows formal LIFF re-entry after a protected 401", async () => {
    const onRedirect = vi.fn();
    const loadContext = vi.fn(async () => {
      throw new Response("unauthorized", { status: 401 });
    });

    await act(async () => {
      root.render(
        <AuthenticatedRouteBoundary
          area="volunteer"
          pathname="/animal-confirmation"
          loadContext={loadContext}
          sessionSource="liff"
          onRedirect={onRedirect}
        >
          <span>protected animal data</span>
        </AuthenticatedRouteBoundary>,
      );
    });

    expect(container.textContent).toContain("重新進入志工入口");
    expect(container.textContent).not.toContain("protected animal data");
    expect(onRedirect).not.toHaveBeenCalled();
  });

  it("fails closed for an expired volunteer membership", async () => {
    const loadContext = vi.fn(async () => ({
      ...result(),
      profile: {
        ...profile,
        memberships: [
          {
            ...profile.memberships[0],
            expires_at: new Date(Date.now() - 1).toISOString(),
          },
        ],
      },
    }));

    await act(async () => {
      root.render(
        <AuthenticatedRouteBoundary
          area="volunteer"
          pathname="/animal-confirmation"
          loadContext={loadContext}
        >
          <span>protected animal data</span>
        </AuthenticatedRouteBoundary>,
      );
    });

    expect(container.textContent).not.toContain("protected animal data");
    expect(container.textContent).toContain("需要確認目前收容所");
  });

  it("keeps credentials during a transient loader failure", async () => {
    window.sessionStorage.setItem("access_token", "access-token");
    const loadContext = vi.fn(async () => {
      throw new Error("network unavailable");
    });

    await act(async () => {
      root.render(
        <AuthenticatedRouteBoundary
          area="management"
          pathname="/"
          loadContext={loadContext}
        >
          <span>management dashboard</span>
        </AuthenticatedRouteBoundary>,
      );
    });

    expect(container.textContent).toContain("服務暫時無法使用");
    expect(window.sessionStorage.getItem("access_token")).toBe("access-token");
  });

  it("ignores an older loader response after a newer route run", async () => {
    let rejectFirst!: (reason: unknown) => void;
    let calls = 0;
    const loadContext = vi.fn(() => {
      calls += 1;
      if (calls === 1) {
        return new Promise<BoundaryLoadResult>((_, reject) => {
          rejectFirst = reject;
        });
      }
      return Promise.resolve(result());
    });

    await act(async () => {
      root.render(
        <AuthenticatedRouteBoundary
          area="volunteer"
          pathname="/animal-confirmation"
          loadContext={loadContext}
        >
          <span>protected animal data</span>
        </AuthenticatedRouteBoundary>,
      );
    });
    await act(async () => {
      root.render(
        <AuthenticatedRouteBoundary
          area="volunteer"
          pathname="/care-report"
          loadContext={loadContext}
        >
          <span>protected animal data</span>
        </AuthenticatedRouteBoundary>,
      );
    });
    await act(async () => {
      rejectFirst(new Response("unauthorized", { status: 401 }));
    });

    expect(container.textContent).toContain("protected animal data");
    expect(container.textContent).not.toContain("重新進入志工入口");
  });
});
