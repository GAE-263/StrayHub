from pathlib import Path

import yaml

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
