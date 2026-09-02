import { cleanupOwnedHandoffTempDirectory } from "./handoff-temp-state.mjs";

export default function cleanupHandoffServer(config) {
  cleanupOwnedHandoffTempDirectory(config.metadata.handoffRunId);
}
