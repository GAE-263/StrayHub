from pathlib import Path

import yaml

GENERATED_TYPES = Path("packages/contracts/src/openapi.ts")


def test_generated_contract_types_exist_for_openapi_source_of_truth() -> None:
    content = GENERATED_TYPES.read_text(encoding="utf-8")

    assert "export interface paths" in content
    assert "CareReportAnswers" in content
    assert "DraftAnswers" in content
    assert "MedicalRecordCreate" in content
    assert "CareReminderSeriesCreate" in content
    assert "OccurrenceAction" in content
    assert '"/v1/management/care-agenda"' in content
    assert '"/v1/care-report-handoffs"' in content
    assert '"/v1/qr-tokens/candidate-organization"' in content
    assert "CareReportHandoffCreateRequest" in content
    assert "CareReportHandoffResponse" in content

    schemas_start = content.index("export interface components")
    operations_start = content.index("export interface operations")
    schemas = content[schemas_start:operations_start]
    list_item_start = schemas.index("        ManagementQrCodeListItem:")
    list_item_end = schemas.index("        };", list_item_start) + len("        };")
    list_item = schemas[list_item_start:list_item_end]
    for field in ("animal_name: string;", "animal_status: string;", "created_at: string;"):
        assert field in list_item
    for field in (
        "shelter_number: string | null;",
        "area_name: string | null;",
        "deep_link: string | null;",
        "token: null;",
    ):
        assert field in list_item
        assert field.replace(":", "?:", 1) not in list_item

    operation_start = content.index("    listManagementQrCodes:")
    operation_end = content.index("    createManagementQrCode:", operation_start)
    operation = content[operation_start:operation_end]
    for parameter in (
        "animal_id?: string;",
        "query?: string;",
        'status?: "all" | "active" | "revoked";',
        'page?: components["parameters"]["Page"];',
        'page_size?: components["parameters"]["PageSize"];',
    ):
        assert parameter in operation


def test_volunteer_access_contract_has_expected_operation_and_schema_surface() -> None:
    feature = yaml.safe_load(
        Path(
            "specs/005-volunteer-access-approval/contracts/volunteer-access.openapi.yaml"
        ).read_text()
    )
    methods = {"get", "post", "patch", "put", "delete"}
    operation_count = sum(
        sum(method in methods for method in path_item) for path_item in feature["paths"].values()
    )
    assert operation_count == 13
    assert len(feature["components"]["schemas"]) == 35
    canonical = Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    for operation_id in (
        "createVolunteerDecisionBatch",
        "updateVolunteerAccessGrant",
        "retryVolunteerNotifications",
    ):
        assert operation_id in canonical


def test_generated_liff_contract_keeps_state_specific_credentials() -> None:
    content = GENERATED_TYPES.read_text(encoding="utf-8")

    for schema in (
        "LiffExchangeNewResponse",
        "LiffExchangePendingResponse",
        "LiffExchangeActiveResponse",
        "LiffExchangeSuspendedResponse",
    ):
        assert f"        {schema}:" in content
    assert 'state: "ACTIVE";' in content
    assert "access_token: string;" in content
    assert "refresh_token: string;" in content

    schemas_start = content.index("export interface components")
    operations_start = content.index("export interface operations")
    schemas = content[schemas_start:operations_start]
    for name in (
        "LiffExchangeNewResponse",
        "LiffExchangePendingResponse",
        "LiffExchangeSuspendedResponse",
    ):
        start = schemas.index(f"        {name}:")
        end = schemas.index("        };", start) + len("        };")
        section = schemas[start:end]
        assert "access_token" not in section
        assert "refresh_token" not in section
        assert "session_id" not in section
