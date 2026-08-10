import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const directory = mkdtempSync(join(tmpdir(), "strayhub-contracts-"));
const generated = join(directory, "openapi.ts");
try {
  const result = spawnSync(
    "npx",
    [
      "openapi-typescript",
      "../../specs/001-volunteer-care-report/contracts/openapi.yaml",
      "-o",
      generated,
    ],
    { stdio: "inherit" },
  );
  if (result.status !== 0) process.exit(result.status ?? 1);

  const expected = readFileSync(generated, "utf8");
  const current = readFileSync("src/openapi.ts", "utf8");
  if (expected !== current) {
    console.error("Generated contract types are stale; run npm run generate.");
    process.exit(1);
  }
} finally {
  rmSync(directory, { recursive: true, force: true });
}
