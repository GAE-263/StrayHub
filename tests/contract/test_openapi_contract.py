from pathlib import Path

import yaml


CONTRACT_PATH = Path("specs/001-volunteer-care-report/contracts/openapi.yaml")


def test_openapi_contract_is_parseable_and_has_required_sections() -> None:
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert document["openapi"].startswith("3.")
    assert "paths" in document
    assert "components" in document
    assert "bearerAuth" in document["components"]["securitySchemes"]


def test_required_paths_and_security_are_declared() -> None:
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    paths = document["paths"]

    required_paths = {
        "/v1/auth/login",
        "/v1/auth/refresh",
        "/v1/auth/liff/exchange",
        "/v1/auth/active-shelter-context",
        "/v1/organizations",
        "/v1/organizations/{organizationId}/initial-admin",
        "/v1/animals/search",
        "/v1/qr-tokens/resolve",
        "/v1/care-report-drafts",
        "/v1/media",
        "/v1/care-reports",
        "/v1/animals/{animalId}/timeline",
        "/v1/observation-options",
        "/v1/care-reports/{reportId}/ai-observations",
        "/v1/ai-observations/{observationId}/review",
        "/v1/line/webhook",
        "/v1/line/bind",
        "/v1/line/rich-menu/context",
        "/v1/line/care-report/drafts/current",
        "/v1/line/care-report/drafts/{draftId}/resume",
        "/v1/line/care-report/drafts/{draftId}/cancel",
    }

    assert required_paths <= paths.keys()
    assert "security" not in paths["/v1/auth/login"]["post"]
    assert "security" not in paths["/v1/auth/refresh"]["post"]
    assert "security" not in paths["/v1/auth/liff/exchange"]["post"]
    assert paths["/v1/care-reports"]["post"]["parameters"][0]["$ref"].endswith(
        "/IdempotencyKey"
    )
    webhook = paths["/v1/line/webhook"]["post"]
    assert webhook["security"] == []
    assert any(
        parameter.get("$ref", "").endswith("/LineSignature")
        for parameter in webhook["parameters"]
    )
    assert webhook["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/LineWebhookRequest"
    )
    assert "原始 Request Body" in webhook["requestBody"]["description"]
    assert "webhookEventId" in document["components"]["schemas"]["LineWebhookEvent"]["required"]


def test_protected_operations_use_bearer_auth_and_unified_errors() -> None:
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    def resolve_response(response: dict) -> dict:
        reference = response.get("$ref")
        if not reference:
            return response
        name = reference.rsplit("/", 1)[-1]
        return document["components"]["responses"][name]

    for path, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            if path in {
                "/v1/auth/login",
                "/v1/auth/refresh",
                "/v1/auth/liff/exchange",
                "/v1/line/webhook",
                "/v1/line/bind",
            }:
                continue

            assert operation.get("security") or document.get("security")
            for status, response in operation.get("responses", {}).items():
                if status.startswith(("4", "5")):
                    assert "ErrorResponse" in str(resolve_response(response))


def test_request_and_response_schemas_are_declared() -> None:
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    schemas = document["components"]["schemas"]

    for path, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            request_body = operation.get("requestBody")
            if request_body:
                assert "content" in request_body
            for response in operation.get("responses", {}).values():
                if "$ref" not in response:
                    for content in response.get("content", {}).values():
                        schema = content.get("schema", {})
                        if "$ref" in schema:
                            assert schema["$ref"].split("/")[-1] in schemas


def test_general_organization_requests_do_not_accept_client_org_scope() -> None:
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    organization_request = document["components"]["schemas"]["OrganizationCreateRequest"]
    assert "org_id" not in organization_request.get("properties", {})
    assert "organization_id" not in organization_request.get("properties", {})


def test_line_contract_does_not_make_client_org_scope_trusted() -> None:
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    for schema_name in ("LineBindRequest", "ResumeDraftRequest"):
        properties = document["components"]["schemas"][schema_name].get("properties", {})
        assert "org_id" not in properties
        assert "organization_id" not in properties
