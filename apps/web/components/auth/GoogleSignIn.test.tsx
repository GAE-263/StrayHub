// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { GoogleSignIn } from "./GoogleSignIn";
const replace = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
const mounted: Array<ReturnType<typeof createRoot>> = [];
beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
});
afterEach(() => {
  act(() => mounted.forEach((root) => root.unmount()));
  mounted.length = 0;
  document.body.replaceChildren();
  sessionStorage.clear();
  window.history.replaceState({}, "", "/");
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});
async function mount() {
  const element = document.createElement("div");
  document.body.appendChild(element);
  const root = createRoot(element);
  mounted.push(root);
  await act(async () => {
    root.render(<GoogleSignIn />);
  });
  return element;
}
it("keeps password login available when Google is disabled", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(Response.json({ enabled: false })),
  );
  const element = await mount();
  expect(element.textContent).toBe("");
});
it.each([null, "00000000-0000-4000-8000-000000000001"])(
  "binds callback to nonce and preserves a join target (%s)",
  async (join) => {
    window.history.replaceState(
      {},
      "",
      join ? `/login?join=${join}` : "/login",
    );
    let callback: ((value: { credential: string }) => void) | undefined;
    const initialize = vi.fn((options) => {
      callback = options.callback;
    });
    vi.stubGlobal("google", {
      accounts: { id: { initialize, renderButton: vi.fn() } },
    });
    const fetch = vi.fn(async (path: string, _init?: RequestInit) => {
      if (path.endsWith("/config")) return Response.json({ enabled: true });
      if (path.endsWith("/transactions"))
        return Response.json({
          transaction_id: "transaction",
          nonce: "nonce",
          csrf_token: "csrf",
          client_id: "client",
        });
      return Response.json({
        access_token: "access",
        refresh_token: "refresh",
        session_id: "session",
      });
    });
    vi.stubGlobal("fetch", fetch);
    const element = await mount();
    expect(initialize).toHaveBeenCalledWith(
      expect.objectContaining({
        nonce: "nonce",
        auto_select: false,
        ux_mode: "popup",
      }),
    );
    await act(async () => {
      callback!({ credential: "sentinel-credential" });
    });
    const call = fetch.mock.calls.find(([path]) => path.endsWith("/exchange"))!;
    expect(call[0]).not.toContain("sentinel");
    expect(JSON.parse(call[1]!.body as string)).toEqual({
      transaction_id: "transaction",
      credential: "sentinel-credential",
    });
    expect(new Headers(call[1]!.headers).get("X-CSRF-Token")).toBe("csrf");
    expect(sessionStorage.getItem("access_token")).toBe("access");
    expect(sessionStorage.getItem("session_source")).toBe("local");
    expect(element.textContent).not.toContain("sentinel-credential");
    expect(replace).toHaveBeenCalledWith(
      join ? `/access?join=${join}` : "/access?entry=1",
    );
  },
);
