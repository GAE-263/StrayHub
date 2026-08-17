import {
  statusLabel,
  type UIStatusKind,
} from "../../components/management/ui-status";

type AIObservationStatusInput = {
  id: string;
  status: string;
};

function aiStatusKind(status: string): UIStatusKind {
  if (status === "running" || status === "pending") return "processing";
  if (status === "failed" || status === "invalid") return "ai-failed";
  return "needs-review";
}

export function reportAIStatusSummary(
  observations: AIObservationStatusInput[],
) {
  return observations.map((observation) => ({
    id: observation.id,
    kind: aiStatusKind(observation.status),
    label: statusLabel(observation.status),
  }));
}
