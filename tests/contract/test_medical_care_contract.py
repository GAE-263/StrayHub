from pathlib import Path

import yaml
from services.api.app.main import app

CANONICAL = Path("specs/001-volunteer-care-report/contracts/openapi.yaml")


def test_medical_care_paths_are_in_runtime_and_canonical_contract() -> None:
    canonical = yaml.safe_load(CANONICAL.read_text(encoding="utf-8"))
    runtime = app.openapi()
    required = {
        "/v1/management/animals/{animalId}/medical-records",
        "/v1/management/medical-records/{recordId}",
        "/v1/management/animals/{animalId}/care-reminder-series",
        "/v1/management/care-reminder-occurrences/{occurrenceId}/actions",
        "/v1/management/care-agenda",
        "/v1/management/care-calendar",
    }
    assert required <= set(canonical["paths"])
    assert required <= set(runtime["paths"])


def test_medical_write_schemas_do_not_accept_client_organization_scope() -> None:
    canonical = yaml.safe_load(CANONICAL.read_text(encoding="utf-8"))
    schemas = canonical["components"]["schemas"]
    for name in ("MedicalRecordCreate", "CareReminderSeriesCreate", "OccurrenceAction"):
        assert "organization_id" not in schemas[name].get("properties", {})
    generated = Path("packages/contracts/src/openapi.ts").read_text(encoding="utf-8")
    assert "CareReminderSeriesCreate" in generated
    assert "OccurrenceAction" in generated


def test_occurrence_action_response_exposes_action_and_completion_evidence() -> None:
    canonical = yaml.safe_load(CANONICAL.read_text(encoding="utf-8"))
    runtime = app.openapi()
    path = "/v1/management/care-reminder-occurrences/{occurrenceId}/actions"
    canonical_operation = canonical["paths"][path]["post"]
    runtime_operation = runtime["paths"][path]["post"]

    assert "409" in canonical_operation["responses"]
    canonical_schema = canonical["components"]["schemas"]["OccurrenceMutation"]
    expected = {
        "action_id",
        "action_type",
        "acted_at",
        "actor_user_id",
        "occurrence_id",
        "status",
        "version",
        "scheduled_at",
        "recorded_at",
        "actual_completed_at",
    }
    assert expected <= set(canonical_schema["required"])

    response_schema = runtime_operation["responses"]["200"]["content"]["application/json"]["schema"]
    runtime_name = response_schema["$ref"].rsplit("/", 1)[-1]
    assert expected <= set(runtime["components"]["schemas"][runtime_name]["required"])
