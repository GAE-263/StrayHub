import { execFile } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { promisify } from "node:util";
import { resolve } from "node:path";
import type { Page } from "@playwright/test";

const execFileAsync = promisify(execFile);

export async function seedMedicalCareFixture(page: Page) {
  const root = resolve(__dirname, "../../../..");
  const databaseUrl =
    process.env.STRAYHUB_TEST_DATABASE_URL ?? process.env.DATABASE_URL;
  if (!databaseUrl)
    throw new Error(
      "setup error: 缺少 STRAYHUB_TEST_DATABASE_URL 或 DATABASE_URL",
    );
  if (process.env.STRAYHUB_MEDICAL_E2E_SEED_ALLOWED !== "1") {
    throw new Error("setup error: 請設定 STRAYHUB_MEDICAL_E2E_SEED_ALLOWED=1");
  }
  const healthUrl = `${process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8001"}/healthz`;
  let healthy = false;
  for (let attempt = 0; attempt < 20; attempt += 1) {
    try {
      const response = await page.request.get(healthUrl);
      if (response.ok()) {
        healthy = true;
        break;
      }
    } catch {
      /* retry */
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 250));
  }
  if (!healthy)
    throw new Error(`setup error: API health check 失敗（${healthUrl}）`);
  const temp = await mkdtemp(resolve(tmpdir(), "strayhub-medical-"));
  const manifest = resolve(temp, "manifest.json");
  await execFileAsync(
    "uv",
    [
      "run",
      "python",
      "-m",
      "scripts.seed_medical_care",
      "--profile",
      "agenda-e2e",
      "--expected-output",
      manifest,
    ],
    {
      cwd: root,
      env: {
        ...process.env,
        STRAYHUB_TEST_DATABASE_URL: databaseUrl,
        STRAYHUB_MEDICAL_E2E_SEED_ALLOWED: "1",
      },
    },
  );
  return {
    manifest,
    cleanup: async () => {
      await execFileAsync(
        "uv",
        [
          "run",
          "python",
          "-m",
          "scripts.seed_medical_care",
          "--profile",
          "agenda-e2e",
          "--clear",
        ],
        {
          cwd: root,
          env: {
            ...process.env,
            STRAYHUB_TEST_DATABASE_URL: databaseUrl,
            STRAYHUB_MEDICAL_E2E_SEED_ALLOWED: "1",
          },
        },
      );
      await rm(temp, { recursive: true, force: true });
    },
  };
}
