from pathlib import Path

import yaml
from services.api.app.main import app

CONTRACT_PATH = Path("specs/001-volunteer-care-report/contracts/openapi.yaml")
MANAGEMENT_PREFIX = "/v1/management/"


def _document() -> dict:
    return yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_management_workbench_paths_cover_the_planned_workflow() -> None:
    paths = _document()["paths"]
    required = {
        "/v1/management/dashboard",
        "/v1/management/animals",
        "/v1/management/animals/{animalId}",
        "/v1/management/reports",
        "/v1/management/reports/{reportId}",
        "/v1/management/reports/{reportId}/correction",
        "/v1/management/reports/{reportId}/archive",
        "/v1/management/reportable-scopes",
        "/v1/management/reportable-scopes/{scopeId}",
        "/v1/management/qr-codes",
        "/v1/management/qr-codes/{qrId}/revoke",
        "/v1/management/ai-review",
        "/v1/management/ai-review/{observationId}/review",
        "/v1/management/audit",
    }

    assert required <= paths.keys()


def test_management_operations_are_protected_and_use_unified_error_contract() -> None:
    document = _document()
    responses = document["components"]["responses"]

    def resolve(response: dict) -> dict:
        if "$ref" not in response:
            return response
        return responses[response["$ref"].rsplit("/", 1)[-1]]

    for path, path_item in document["paths"].items():
        if not path.startswith(MANAGEMENT_PREFIX):
            continue
        for method, operation in path_item.items():
            if method not in {"get", "post", "patch"}:
                continue
            assert operation.get("security") or document.get("security")
            for code, response in operation["responses"].items():
                if code.startswith("4") or code.startswith("5"):
                    assert "ErrorResponse" in str(resolve(response))


def test_management_report_mutations_are_traceable_and_audit_is_read_only() -> None:
    paths = _document()["paths"]
    assert "delete" not in paths["/v1/management/reports/{reportId}"]
    assert "delete" not in paths["/v1/management/reports/{reportId}/archive"]
    assert set(paths["/v1/management/audit"]) == {"get"}


def test_management_write_schemas_do_not_accept_client_organization_scope() -> None:
    schemas = _document()["components"]["schemas"]
    write_schemas = {
        "ManagementReportCorrectionRequest",
        "ManagementArchiveRequest",
        "ManagementReportableScopeRequest",
        "ManagementReportableScopeUpdateRequest",
        "ManagementQrCodeRequest",
    }

    for name in write_schemas:
        properties = schemas[name].get("properties", {})
        assert "org_id" not in properties
        assert "organization_id" not in properties


def test_qr_management_list_contract_is_animal_aware_paginated_and_server_scoped() -> None:
    document = _document()
    operation = document["paths"]["/v1/management/qr-codes"]["get"]
    parameters = {
        parameter["name"]: parameter
        for parameter in operation["parameters"]
        if "$ref" not in parameter
    }
    references = {parameter.get("$ref") for parameter in operation["parameters"]}

    assert set(parameters) == {"animal_id", "query", "status"}
    assert parameters["status"]["schema"] == {
        "type": "string",
        "enum": ["all", "active", "revoked"],
        "default": "all",
    }
    assert parameters["query"]["schema"]["maxLength"] == 200
    assert "#/components/parameters/Page" in references
    assert "#/components/parameters/PageSize" in references
    assert "organization_id" not in parameters
    assert "422" in operation["responses"]

    schemas = document["components"]["schemas"]
    response = schemas["ManagementQrCodeList"]
    assert set(response["required"]) == {"items", "page", "page_size", "total"}
    assert response["properties"]["items"]["items"]["$ref"].endswith("/ManagementQrCodeListItem")
    item = schemas["ManagementQrCodeListItem"]
    expected_fields = {
        "id",
        "organization_id",
        "animal_id",
        "animal_name",
        "shelter_number",
        "animal_status",
        "area_name",
        "status",
        "revoked",
        "created_at",
        "deep_link",
        "token",
    }
    assert set(item["required"]) == expected_fields
    assert set(item["properties"]) == expected_fields
    assert item["properties"]["shelter_number"]["type"] == ["string", "null"]
    assert item["properties"]["area_name"]["type"] == ["string", "null"]
    assert item["properties"]["created_at"]["format"] == "date-time"

    # Mutation responses keep using the existing QR-only schema.
    for path in (
        "/v1/management/qr-codes/{qrId}/revoke",
        "/v1/management/qr-codes/{qrId}/regenerate",
    ):
        schema = document["paths"][path]["post"]["responses"]["200"]["content"]
        assert schema["application/json"]["schema"]["$ref"].endswith("/ManagementQrCode")


def test_qr_management_runtime_model_matches_canonical_list_fields() -> None:
    canonical = _document()
    runtime = app.openapi()
    runtime_operation = runtime["paths"]["/v1/management/qr-codes"]["get"]
    runtime_query_parameters = {
        parameter["name"]: parameter["schema"]
        for parameter in runtime_operation["parameters"]
        if parameter["in"] == "query"
    }
    assert set(runtime_query_parameters) == {"animal_id", "query", "status", "page", "page_size"}
    assert runtime_query_parameters["status"]["enum"] == ["all", "active", "revoked"]
    assert runtime_query_parameters["status"]["default"] == "all"
    assert runtime_query_parameters["page"]["default"] == 1
    assert runtime_query_parameters["page"]["minimum"] == 1
    assert runtime_query_parameters["page_size"]["default"] == 20
    assert runtime_query_parameters["page_size"]["minimum"] == 1
    assert runtime_query_parameters["page_size"]["maximum"] == 100

    canonical_item = canonical["components"]["schemas"]["ManagementQrCodeListItem"]
    runtime_item = runtime["components"]["schemas"]["ManagementQrCodeListItem"]
    assert set(runtime_item["required"]) == set(canonical_item["required"])
    assert set(runtime_item["properties"]) == set(canonical_item["properties"])
    assert runtime_item["properties"]["status"]["enum"] == ["active", "revoked"]
    for field in ("shelter_number", "area_name", "deep_link"):
        assert {member["type"] for member in runtime_item["properties"][field]["anyOf"]} == {
            "string",
            "null",
        }
    assert runtime_item["properties"]["token"]["type"] == "null"

    runtime_list = runtime["components"]["schemas"]["ManagementQrCodeListResponse"]
    canonical_list = canonical["components"]["schemas"]["ManagementQrCodeList"]
    assert set(runtime_list["required"]) == set(canonical_list["required"])
    assert set(runtime_list["properties"]) == set(canonical_list["properties"])
    assert runtime_list["properties"]["page"]["minimum"] == 1
    assert runtime_list["properties"]["page_size"]["minimum"] == 1
    assert runtime_list["properties"]["page_size"]["maximum"] == 100
    assert runtime_list["properties"]["total"]["minimum"] == 0
