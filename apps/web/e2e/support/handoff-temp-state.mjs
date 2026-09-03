import {
  existsSync,
  readFileSync,
  rmSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { basename, isAbsolute, join, relative, resolve, sep } from "node:path";

const directoryPrefix = "strayhub-liff-handoff-";
const markerPrefix = "strayhub-liff-handoff-owner-";
const runIdPattern = /^[0-9a-f-]{36}$/i;
const excludedRoots = new Set([
  ".next",
  ".next-liff-handoff-e2e",
  "node_modules",
  "playwright-report",
  "test-results",
]);

function assertRunId(runId) {
  if (typeof runId !== "string" || !runIdPattern.test(runId)) {
    throw new Error("Invalid handoff E2E run identifier");
  }
}

function markerPath(runId) {
  assertRunId(runId);
  return join(tmpdir(), `${markerPrefix}${runId}.json`);
}

function assertOwnedDirectory(runId, directory) {
  const resolvedTemp = resolve(tmpdir());
  const resolvedDirectory = resolve(directory);
  const pathFromTemp = relative(resolvedTemp, resolvedDirectory);
  if (
    !pathFromTemp ||
    pathFromTemp.startsWith(`..${sep}`) ||
    pathFromTemp === ".." ||
    isAbsolute(pathFromTemp) ||
    !basename(resolvedDirectory).startsWith(`${directoryPrefix}${runId}-`)
  ) {
    throw new Error("Invalid handoff E2E temporary directory ownership");
  }
  return resolvedDirectory;
}

export function registerOwnedHandoffTempDirectory(runId, directory) {
  assertRunId(runId);
  const ownedDirectory = assertOwnedDirectory(runId, directory);
  writeFileSync(
    markerPath(runId),
    JSON.stringify({ directory: ownedDirectory }),
    {
      encoding: "utf8",
      flag: "wx",
      mode: 0o600,
    },
  );
}

export function cleanupOwnedHandoffTempDirectory(runId) {
  assertRunId(runId);
  const ownedMarker = markerPath(runId);
  if (!existsSync(ownedMarker)) return;
  const parsed = JSON.parse(readFileSync(ownedMarker, "utf8"));
  const ownedDirectory = assertOwnedDirectory(runId, parsed.directory);
  rmSync(ownedDirectory, {
    recursive: true,
    force: true,
    maxRetries: 10,
    retryDelay: 100,
  });
  unlinkSync(ownedMarker);
}

export function shouldCopyHandoffSource(projectRoot, source) {
  const pathFromRoot = relative(projectRoot, source);
  if (!pathFromRoot) return true;
  const topLevelName = pathFromRoot.split(sep)[0];
  if (excludedRoots.has(topLevelName)) return false;
  if (topLevelName === ".env.example") return true;
  return !topLevelName.startsWith(".env");
}
