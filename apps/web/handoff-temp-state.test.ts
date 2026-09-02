import { randomUUID } from "node:crypto";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import {
  cleanupOwnedHandoffTempDirectory,
  registerOwnedHandoffTempDirectory,
  shouldCopyHandoffSource,
} from "./e2e/support/handoff-temp-state.mjs";

const ownedRuns: Array<{ runId: string; directory: string }> = [];

afterEach(() => {
  for (const item of ownedRuns.splice(0)) {
    cleanupOwnedHandoffTempDirectory(item.runId);
    rmSync(item.directory, { recursive: true, force: true });
  }
});

function createOwnedRun() {
  const runId = randomUUID();
  const directory = mkdtempSync(
    join(tmpdir(), `strayhub-liff-handoff-${runId}-`),
  );
  registerOwnedHandoffTempDirectory(runId, directory);
  ownedRuns.push({ runId, directory });
  return { runId, directory };
}

describe("handoff E2E temporary ownership", () => {
  it("cleans only the requesting run's exact directory", () => {
    const runA = createOwnedRun();
    const runB = createOwnedRun();

    cleanupOwnedHandoffTempDirectory(runB.runId);

    expect(existsSync(runA.directory)).toBe(true);
    expect(existsSync(runB.directory)).toBe(false);
  });

  it("excludes local environment secrets without excluding the safe example", () => {
    const projectRoot = join(tmpdir(), "handoff-copy-filter-project");

    expect(
      shouldCopyHandoffSource(projectRoot, join(projectRoot, ".env")),
    ).toBe(false);
    expect(
      shouldCopyHandoffSource(projectRoot, join(projectRoot, ".env.local")),
    ).toBe(false);
    expect(
      shouldCopyHandoffSource(
        projectRoot,
        join(projectRoot, ".env.development.local"),
      ),
    ).toBe(false);
    expect(
      shouldCopyHandoffSource(
        projectRoot,
        join(projectRoot, ".env.development"),
      ),
    ).toBe(false);
    expect(
      shouldCopyHandoffSource(projectRoot, join(projectRoot, ".env.example")),
    ).toBe(true);
    expect(shouldCopyHandoffSource(projectRoot, join(projectRoot, "app"))).toBe(
      true,
    );
  });
});
