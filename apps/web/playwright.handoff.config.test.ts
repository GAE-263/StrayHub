import { describe, expect, it } from "vitest";

import config from "./playwright.handoff.config";

describe("handoff Playwright isolation", () => {
  it("uses only the handoff spec on a fresh dedicated mock server", () => {
    expect(config.testMatch).toBe("animal-confirmation-qr.spec.ts");
    expect(config.globalTeardown).toBe(
      "./e2e/support/cleanup-handoff-server.mjs",
    );
    expect(config.use?.baseURL).toBe("http://127.0.0.1:3002");
    expect(Array.isArray(config.webServer)).toBe(false);

    const webServer = Array.isArray(config.webServer)
      ? undefined
      : config.webServer;
    expect(webServer).toMatchObject({
      command: "node e2e/support/start-handoff-server.mjs 3002",
      url: "http://127.0.0.1:3002",
      reuseExistingServer: false,
      env: { LIFF_HANDOFF_E2E_MOCK: "1" },
    });
    expect(webServer?.env?.STRAYHUB_LIFF_HANDOFF_RUN_ID).toBe(
      config.metadata?.handoffRunId,
    );
  });
});
