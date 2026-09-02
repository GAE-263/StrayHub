import { cpSync, mkdtempSync, realpathSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import {
  cleanupOwnedHandoffTempDirectory,
  registerOwnedHandoffTempDirectory,
  shouldCopyHandoffSource,
} from "./handoff-temp-state.mjs";

const supportDirectory = dirname(fileURLToPath(import.meta.url));
const projectRoot = realpathSync(resolve(supportDirectory, "../.."));
const port = process.argv[2] ?? "3002";
const runId = process.env.STRAYHUB_LIFF_HANDOFF_RUN_ID;
if (!runId) throw new Error("Missing STRAYHUB_LIFF_HANDOFF_RUN_ID");
const temporaryRoot = mkdtempSync(
  join(tmpdir(), `strayhub-liff-handoff-${runId}-`),
);
registerOwnedHandoffTempDirectory(runId, temporaryRoot);

try {
  cpSync(projectRoot, temporaryRoot, {
    recursive: true,
    filter: (source) => shouldCopyHandoffSource(projectRoot, source),
  });
  symlinkSync(
    join(projectRoot, "node_modules"),
    join(temporaryRoot, "node_modules"),
    "dir",
  );
} catch (error) {
  cleanupOwnedHandoffTempDirectory(runId);
  throw error;
}

const nextCli = join(projectRoot, "node_modules/next/dist/bin/next");
const child = spawn(
  process.execPath,
  [nextCli, "dev", "--hostname", "127.0.0.1", "--port", port],
  {
    cwd: temporaryRoot,
    env: process.env,
    stdio: "inherit",
  },
);

let stopping = false;
const stop = (signal) => {
  if (stopping) return;
  stopping = true;
  if (child.exitCode === null) child.kill(signal);
};

process.once("SIGINT", () => stop("SIGINT"));
process.once("SIGTERM", () => stop("SIGTERM"));

child.once("exit", (code, signal) => {
  cleanupOwnedHandoffTempDirectory(runId);
  if (code !== null) {
    process.exitCode = code;
  } else if (signal && !stopping) {
    process.exitCode = 1;
  }
});
