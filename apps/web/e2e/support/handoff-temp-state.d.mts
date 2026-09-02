export function registerOwnedHandoffTempDirectory(
  runId: string,
  directory: string,
): void;

export function cleanupOwnedHandoffTempDirectory(runId: string): void;

export function shouldCopyHandoffSource(
  projectRoot: string,
  source: string,
): boolean;
