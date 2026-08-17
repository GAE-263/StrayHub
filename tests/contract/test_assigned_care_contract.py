from pathlib import Path

import yaml
from services.api.app.main import app

CANONICAL = Path("specs/001-volunteer-care-report/contracts/openapi.yaml")
ASSIGNED_PATHS = {
    "/v1/assigned-care-reminders",
    "/v1/assigned-care-reminders/{occurrenceId}",
    "/v1/assigned-care-reminders/{occurrenceId}/actions",
}
ITEM_FIELDS = {
    "occurrence_id",
    "version",
    "status",
    "animal",
    "reminder_type",
    "title",
    "instructions",
    "display_local_at",
    "can_complete",
    "can_skip",
}
FORBIDDEN_FIELDS = {
    "organization_id",
    "series_id",
    "lineage_id",
    "clinic",
    "veterinarian",
    "weight_kg",
    "attachments",
    "medical_records",
    "assignee_membership_id",
}


def test_assigned_paths_exist_in_runtime_canonical_and_generated_contracts() -> None:
    canonical = yaml.safe_load(CANONICAL.read_text(encoding="utf-8"))
    runtime = app.openapi()
    generated = Path("packages/contracts/src/openapi.ts").read_text(encoding="utf-8")

    assert ASSIGNED_PATHS <= set(canonical["paths"])
    assert ASSIGNED_PATHS <= set(runtime["paths"])
    for path in ASSIGNED_PATHS:
        assert f'"{path}"' in generated


def test_assigned_item_schema_is_an_exact_minimum_projection() -> None:
    canonical = yaml.safe_load(CANONICAL.read_text(encoding="utf-8"))
    runtime = app.openapi()

    canonical_item = canonical["components"]["schemas"]["AssignedCareItem"]
    runtime_item = runtime["components"]["schemas"]["AssignedCareItemResponse"]
    assert canonical_item["additionalProperties"] is False
    assert runtime_item["additionalProperties"] is False
    assert set(canonical_item["properties"]) == ITEM_FIELDS
    assert set(runtime_item["properties"]) == ITEM_FIELDS
    assert FORBIDDEN_FIELDS.isdisjoint(canonical_item["properties"])
    assert FORBIDDEN_FIELDS.isdisjoint(runtime_item["properties"])


def test_assigned_action_only_accepts_complete_or_skip_and_returns_server_times() -> None:
    canonical = yaml.safe_load(CANONICAL.read_text(encoding="utf-8"))
    runtime = app.openapi()

    request = canonical["components"]["schemas"]["AssignedCareAction"]
    assert request["properties"]["action"]["enum"] == ["complete", "skip"]
    assert "organization_id" not in request["properties"]

    mutation = canonical["components"]["schemas"]["AssignedCareMutation"]
    assert {
        "occurrence",
        "action_id",
        "action_type",
        "acted_at",
        "recorded_at",
        "actual_completed_at",
    } <= set(mutation["required"])
    runtime_mutation = runtime["components"]["schemas"]["AssignedCareMutationResponse"]
    assert set(mutation["properties"]) == set(runtime_mutation["properties"])
