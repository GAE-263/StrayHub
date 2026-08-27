export type VolunteerLiffEntryIntent = {
  view: "application" | "status";
  organizationId?: string;
  shelterEntryReference?: string;
  targetConflict: boolean;
};

const MAX_LIFF_STATE_LENGTH = 2048;

type Target =
  { kind: "organization"; value: string } | { kind: "entry"; value: string };

type ParsedTarget = { target?: Target; ambiguous: boolean };

function targetFrom(params: URLSearchParams): ParsedTarget {
  const organizationId = params.get("organization_id")?.trim();
  const entryReference =
    params.get("shelter_entry_reference")?.trim() ||
    params.get("entry")?.trim();
  if (organizationId && entryReference) return { ambiguous: true };
  if (organizationId)
    return {
      target: { kind: "organization", value: organizationId },
      ambiguous: false,
    };
  if (entryReference)
    return {
      target: { kind: "entry", value: entryReference },
      ambiguous: false,
    };
  return { ambiguous: false };
}

function stateParams(rawState: string | null): URLSearchParams {
  if (
    !rawState ||
    rawState.length > MAX_LIFF_STATE_LENGTH ||
    !rawState.startsWith("?")
  ) {
    return new URLSearchParams();
  }
  return new URLSearchParams(rawState.slice(1));
}

function sameTarget(left: Target, right: Target): boolean {
  return left.kind === right.kind && left.value === right.value;
}

export function parseVolunteerLiffEntryIntent(
  input: URLSearchParams | string,
): VolunteerLiffEntryIntent {
  const direct = typeof input === "string" ? new URLSearchParams(input) : input;
  const state = stateParams(direct.get("liff.state"));
  const directView = direct.get("view");
  const stateView = state.get("view");
  const view =
    directView === "status" || directView === "application"
      ? directView
      : stateView === "status" || stateView === "application"
        ? stateView
        : "application";
  const directTarget = targetFrom(direct);
  const stateTarget = targetFrom(state);
  const targetConflict = Boolean(
    directTarget.ambiguous ||
    stateTarget.ambiguous ||
    (directTarget.target &&
      stateTarget.target &&
      !sameTarget(directTarget.target, stateTarget.target)),
  );
  const target = targetConflict
    ? undefined
    : (directTarget.target ?? stateTarget.target);

  return {
    view,
    ...(target?.kind === "organization"
      ? { organizationId: target.value }
      : {}),
    ...(target?.kind === "entry"
      ? { shelterEntryReference: target.value }
      : {}),
    targetConflict,
  };
}
