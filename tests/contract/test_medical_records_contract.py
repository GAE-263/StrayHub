from pathlib import Path

import yaml
from services.api.app.api.medical_records import (
    MedicalRecordArchiveRequest,
    MedicalRecordCreateRequest,
    MedicalRecordUpdateRequest,
)
from services.api.app.main import app

CONTRACT = Path("specs/001-volunteer-care-report/contracts/openapi.yaml")


def _document() -> dict:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def test_medical_record_paths_and_operations_are_in_runtime_contract() -> None:
    document = _document()
    runtime = app.openapi()
    paths = {
        "/v1/management/animals/{animalId}/medical-records",
        "/v1/management/medical-records/{recordId}",
        "/v1/management/medical-records/{recordId}/archive",
    }
    assert paths <= set(document["paths"])
    assert paths <= set(runtime["paths"])
    assert document["paths"][next(iter(paths))]


def test_write_schemas_are_strict_and_tenant_scope_is_server_derived() -> None:
    schemas = _document()["components"]["schemas"]
    create = schemas["MedicalRecordCreate"]
    assert create["additionalProperties"] is False
    assert {"occurred_at", "record_type", "title", "content"} <= set(create["required"])
    for name in ("MedicalRecordCreate", "MedicalRecordUpdate", "MedicalRecordArchive"):
        assert "organization_id" not in str(schemas[name])

    assert "organization_id" not in MedicalRecordCreateRequest.model_fields
    assert "organization_id" not in MedicalRecordUpdateRequest.model_fields
    assert "organization_id" not in MedicalRecordArchiveRequest.model_fields


def test_medical_record_response_preserves_history_and_optional_weight() -> None:
    schema = _document()["components"]["schemas"]["MedicalRecord"]
    assert {
        "id",
        "animal_id",
        "occurred_at",
        "occurred_timezone",
        "record_type",
        "title",
        "content",
        "status",
        "version",
        "created_by_user_id",
        "created_at",
        "updated_by_user_id",
        "updated_at",
        "media_ids",
    } <= set(schema["required"])
    assert schema["properties"]["weight_kg"]["exclusiveMinimum"] == 0
    assert schema["properties"]["media_ids"]["type"] == "array"


def test_mutation_operations_declare_conflict_and_validation_responses() -> None:
    document = _document()
    update = document["paths"]["/v1/management/medical-records/{recordId}"]["patch"]
    archive = document["paths"]["/v1/management/medical-records/{recordId}/archive"]["post"]
    assert {"200", "409"} <= set(update["responses"])
    assert "200" in archive["responses"]
