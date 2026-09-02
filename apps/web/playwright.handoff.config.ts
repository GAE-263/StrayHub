import { defineConfig, devices } from "@playwright/test";
import { randomUUID } from "node:crypto";

const port = 3002;
const handoffRunId = randomUUID();

export default defineConfig({
  testDir: "./e2e",
  testMatch: "animal-confirmation-qr.spec.ts",
  globalTeardown: "./e2e/support/cleanup-handoff-server.mjs",
  metadata: { handoffRunId },
  timeout: 30_000,
  fullyParallel: true,
  reporter: process.env.CI ? [["line"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `node e2e/support/start-handoff-server.mjs ${port}`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
    env: {
      LIFF_HANDOFF_E2E_MOCK: "1",
      STRAYHUB_LIFF_HANDOFF_RUN_ID: handoffRunId,
    },
  },
});
