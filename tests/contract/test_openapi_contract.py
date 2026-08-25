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
        "/v1/care-report-handoffs",
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
    assert paths["/v1/auth/login"]["post"]["security"] == []
    assert paths["/v1/auth/refresh"]["post"]["security"] == []
    assert paths["/v1/auth/liff/exchange"]["post"]["security"] == []
    assert paths["/v1/care-reports"]["post"]["parameters"][0]["$ref"].endswith("/IdempotencyKey")
    webhook = paths["/v1/line/webhook"]["post"]
    assert webhook["security"] == []
    assert any(
        parameter.get("$ref", "").endswith("/LineSignature") for parameter in webhook["parameters"]
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

    for _path, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            if _path in {
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

    for _path, path_item in document["paths"].items():
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


def test_liff_exchange_uses_state_discriminated_response_contract() -> None:
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    schemas = document["components"]["schemas"]
    response = schemas["LiffExchangeResponse"]

    assert response["discriminator"]["propertyName"] == "state"
    assert {item["$ref"].rsplit("/", 1)[-1] for item in response["oneOf"]} == {
        "LiffExchangeNewResponse",
        "LiffExchangePendingResponse",
        "LiffExchangeActiveResponse",
        "LiffExchangeSuspendedResponse",
    }

    credential_fields = {"access_token", "refresh_token", "expires_in", "session_id", "user_id"}
    active = schemas["LiffExchangeActiveResponse"]
    assert credential_fields <= set(active["required"])
    assert active["properties"]["state"]["const"] == "ACTIVE"

    for name, state in (
        ("LiffExchangeNewResponse", "NEW"),
        ("LiffExchangePendingResponse", "PENDING"),
        ("LiffExchangeSuspendedResponse", "SUSPENDED"),
    ):
        schema = schemas[name]
        assert schema["additionalProperties"] is False
        assert schema["properties"]["state"]["const"] == state
        assert not credential_fields & schema["properties"].keys()

    responses = document["paths"]["/v1/auth/liff/exchange"]["post"]["responses"]
    assert responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/LiffExchangeResponse"
    }
    assert set(responses) >= {"200", "401", "403", "422", "503"}


def test_liff_exchange_uses_route_specific_safe_errors() -> None:
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    responses = document["paths"]["/v1/auth/liff/exchange"]["post"]["responses"]
    schemas = document["components"]["schemas"]

    assert responses["401"]["$ref"].endswith("/LiffIdentityRejected")
    assert responses["403"]["$ref"].endswith("/LiffEntryUnavailable")
    for name, code, message in (
        ("LiffIdentityError", "invalid_line_id_token", "無法確認 LINE 身分"),
        ("LiffEntryUnavailableError", "entry_unavailable", "此志工入口目前無法使用"),
    ):
        schema = schemas[name]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == {"code", "message", "request_id"}
        assert schema["properties"]["code"]["const"] == code
        assert schema["properties"]["message"]["const"] == message
        assert "details" not in schema["properties"]


def test_004_additive_contract_matches_canonical_liff_boundary() -> None:
    canonical = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    additive = yaml.safe_load(
        Path(
            "specs/004-volunteer-entry-route-isolation/contracts/liff-exchange.openapi.yaml"
        ).read_text(encoding="utf-8")
    )
    canonical_request = canonical["components"]["schemas"]["LiffExchangeRequest"]
    additive_request = additive["components"]["schemas"]["LiffExchangeRequest"]

    assert additive_request["required"] == canonical_request["required"]
    assert additive_request["additionalProperties"] is canonical_request["additionalProperties"]
    for field in ("id_token", "shelter_entry_reference"):
        assert (
            additive_request["properties"][field]["minLength"]
            == canonical_request["properties"][field]["minLength"]
        )
        assert (
            additive_request["properties"][field]["maxLength"]
            == canonical_request["properties"][field]["maxLength"]
        )
    additive_responses = additive["paths"]["/v1/auth/liff/exchange"]["post"]["responses"]
    canonical_responses = canonical["paths"]["/v1/auth/liff/exchange"]["post"]["responses"]
    for status in ("200", "401", "403", "422", "503"):
        assert status in additive_responses
        assert status in canonical_responses


def test_care_answers_distinguish_partial_draft_and_complete_report() -> None:
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    schemas = document["components"]["schemas"]
    draft = schemas["DraftAnswers"]
    complete = schemas["CareReportAnswers"]
    required = {
        "care_completion",
        "walk_completion",
        "feeding",
        "water",
        "activity",
        "urination",
        "defecation",
        "resource_guarding",
        "human_interaction",
        "animal_interaction",
        "emotion",
        "walk_reaction",
        "appearance_special_status",
    }

    assert not draft.get("required")
    assert "answering_completion" in schemas["Draft"]["properties"]["current_step"]["enum"]
    assert required <= set(complete["allOf"][1]["required"])
    assert schemas["CareReportCreateRequest"]["properties"]["observations"]["$ref"].endswith(
        "/CareReportAnswers"
    )
