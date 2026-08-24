import asyncio
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import ValidationError
from services.api.app.api.errors import request_validation_error_handler
from services.api.app.api.volunteer_access import (
    ExplicitVolunteerDecisionSelection,
    GrantPeriodUpdateRequest,
    GrantRevokeRequest,
    VolunteerApplicationBatchFilter,
    VolunteerApplicationCreateRequest,
    VolunteerApplicationDetailResponse,
    VolunteerApplicationWithdrawRequest,
    VolunteerDecisionItemResponse,
    VolunteerIdentityRequest,
    VolunteerNotificationRetryRequest,
    VolunteerPiiRevealRequest,
    VolunteerPiiRevealResponse,
    router,
)
from services.api.app.main import app
from sqlalchemy.exc import SQLAlchemyError


def test_application_contract_declares_status_submit_withdraw_and_safe_errors() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    paths = document["paths"]
    status = paths["/v1/volunteer-applications/status"]["post"]
    assert status["operationId"] == ("resolveVolunteerApplicationStatus")
    assert status["security"] == []
    assert "401" in status["responses"]
    submit = paths["/v1/volunteer-applications"]["post"]
    assert submit["security"] == []
    assert {"200", "201", "401", "403", "409", "422", "503"} <= submit["responses"].keys()
    withdraw = paths["/v1/volunteer-applications/{applicationId}/withdraw"]["post"]
    assert withdraw["security"] == []
    assert {"200", "401", "404", "409", "422", "503"} <= withdraw["responses"].keys()
    assert paths["/v1/public/volunteer-organizations"]["get"]["security"] == []


def test_masked_detail_and_explicit_pii_reveal_contracts_are_separate() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    paths = document["paths"]
    detail_path = "/v1/organizations/{organizationId}/volunteer-applications/{applicationId}"
    reveal_path = f"{detail_path}/pii-reveal"

    assert paths[detail_path]["get"]["operationId"] == "getVolunteerApplicationDetail"
    assert paths[reveal_path]["post"]["operationId"] == "revealVolunteerApplicationPii"
    assert {"401", "403", "404", "503"} <= paths[detail_path]["get"]["responses"].keys()
    assert {"401", "403", "404", "410", "422", "503"} <= paths[reveal_path]["post"][
        "responses"
    ].keys()

    schemas = document["components"]["schemas"]
    detail = schemas["VolunteerApplicationDetailResponse"]
    reveal_request = schemas["VolunteerPiiRevealRequest"]
    reveal_response = schemas["VolunteerPiiRevealResponse"]
    assert detail["additionalProperties"] is False
    assert reveal_request["additionalProperties"] is False
    assert reveal_response["additionalProperties"] is False
    assert reveal_request["required"] == ["purpose_code"]
    assert reveal_request["properties"]["purpose_code"]["const"] == "application_review"
    assert {"applicant_name", "phone_number", "basic_profile"} <= set(
        reveal_response["properties"]
    )
    assert not {"applicant_name", "phone_number", "basic_profile"} & set(detail["properties"])

    assert VolunteerPiiRevealRequest.model_validate(
        {"purpose_code": "application_review"}
    ).purpose_code == "application_review"
    with pytest.raises(ValidationError):
        VolunteerPiiRevealRequest.model_validate({"purpose_code": "other"})
    assert set(VolunteerPiiRevealResponse.model_fields) == {
        "applicant_name",
        "phone_number",
        "basic_profile",
    }
    assert VolunteerApplicationDetailResponse.model_config["extra"] == "forbid"

    routes = {
        (route.path, method)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
    }
    assert (detail_path, "GET") in routes
    assert (reveal_path, "POST") in routes


def test_date_scoped_management_contract_requires_explicit_review_date() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    schemas = document["components"]["schemas"]

    assert "available_service_dates" in schemas["VolunteerApplicationListResponse"]["required"]
    assert "service_date" in schemas["ExplicitVolunteerDecisionSelection"]["required"]
    assert schemas["VolunteerApplicationBatchFilter"]["properties"]["unassigned"] == {
        "type": "boolean"
    }
    assert len(schemas["VolunteerApplicationBatchFilter"]["oneOf"]) == 2
    assert len(VolunteerApplicationBatchFilter.model_json_schema()["oneOf"]) == 2
    assert "expected_version" in schemas["VolunteerDecisionItemResponse"]["required"]
    response_item = VolunteerDecisionItemResponse.model_validate(
        {
            "application_id": "00000000-0000-0000-0000-000000000001",
            "expected_version": 2,
            "result": "failed",
        }
    )
    assert response_item.model_dump()["expected_version"] == 2
    review_filter = VolunteerApplicationBatchFilter(
        status="pending",
        service_date=date(2026, 8, 25),
        submitted_from=datetime(2026, 8, 24, tzinfo=timezone.utc),
    )
    repository_filters = review_filter.to_repository_filters()
    assert repository_filters["service_date"] == date(2026, 8, 25)
    assert repository_filters["submitted_from"] == datetime(
        2026, 8, 24, tzinfo=timezone.utc
    )
    for invalid_filter in (
        {"status": "pending"},
        {"status": "pending", "service_date": "2026-08-25", "unassigned": True},
    ):
        with pytest.raises(ValidationError):
            VolunteerApplicationBatchFilter.model_validate(invalid_filter)
    with pytest.raises(ValidationError):
        ExplicitVolunteerDecisionSelection.model_validate(
            {
                "mode": "explicit_items",
                "items": [
                    {
                        "application_id": "00000000-0000-0000-0000-000000000001",
                        "expected_version": 1,
                    }
                ],
            }
        )


def test_app_normalizes_database_failures_to_dependency_unavailable() -> None:
    assert SQLAlchemyError in app.exception_handlers


def test_app_sanitizes_request_validation_errors() -> None:
    assert app.exception_handlers[RequestValidationError] is request_validation_error_handler


@pytest.mark.asyncio
async def test_validation_error_response_does_not_echo_sensitive_target_values() -> None:
    raw_token = "raw-line-id-token-must-not-echo"
    raw_reference = "raw-entry-reference-must-not-echo"
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/volunteer-applications/status",
            "headers": [],
        }
    )

    response = await request_validation_error_handler(request, RequestValidationError([]))

    assert response.status_code == 422
    assert raw_token not in response.body.decode()
    assert raw_reference not in response.body.decode()


def test_validation_error_response_does_not_reflect_caller_request_id() -> None:
    raw_request_id = "caller-secret-must-not-echo"
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/volunteer-applications/status",
            "headers": [(b"x-request-id", raw_request_id.encode())],
        }
    )

    response = asyncio.run(request_validation_error_handler(request, RequestValidationError([])))

    assert raw_request_id not in response.body.decode()


def test_application_router_and_payloads_match_canonical_contract() -> None:
    routes = {
        (route.path, method)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
    }
    assert ("/v1/volunteer-applications/status", "POST") in routes
    assert ("/v1/volunteer-applications", "POST") in routes
    assert ("/v1/volunteer-applications/{applicationId}/withdraw", "POST") in routes
    assert set(VolunteerIdentityRequest.model_fields) == {
        "id_token",
        "organization_id",
        "shelter_entry_reference",
    }
    assert VolunteerIdentityRequest.model_fields["organization_id"].default is None
    assert VolunteerIdentityRequest.model_fields["shelter_entry_reference"].default is None
    assert set(VolunteerApplicationCreateRequest.model_fields) == {
        "id_token",
        "organization_id",
        "shelter_entry_reference",
        "applicant_name",
        "phone_number",
        "basic_profile",
        "insurance_identity",
        "insurance_consent_acknowledged",
        "client_request_id",
        "consent_acknowledged",
        "service_dates",
    }
    assert set(VolunteerApplicationWithdrawRequest.model_fields) == {
        "id_token",
        "shelter_entry_reference",
        "expected_version",
    }
    assert VolunteerApplicationCreateRequest.model_fields["consent_acknowledged"].is_required()
    assert VolunteerApplicationWithdrawRequest.model_fields["expected_version"].is_required()


def test_management_application_filter_accepts_a_service_date() -> None:
    payload = VolunteerApplicationBatchFilter.model_validate(
        {"status": "pending", "service_date": "2026-08-20"}
    )

    assert payload.service_date is not None
    assert payload.service_date.isoformat() == "2026-08-20"


def test_public_volunteer_organization_directory_and_identity_schema_are_canonical() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    paths = document["paths"]
    assert paths["/v1/public/volunteer-organizations"]["get"]["operationId"] == (
        "listPublicVolunteerOrganizations"
    )
    schemas = document["components"]["schemas"]
    identity = schemas["VolunteerIdentityRequest"]
    assert identity["required"] == ["id_token"]
    assert identity["additionalProperties"] is False
    assert len(identity["oneOf"]) == 2
    assert {tuple(branch["required"]) for branch in identity["oneOf"]} == {
        ("organization_id",),
        ("shelter_entry_reference",),
    }
    public = schemas["PublicVolunteerOrganization"]
    assert public["required"] == ["id", "code", "name", "service_area", "insurance_required"]
    assert public["additionalProperties"] is False
    assert set(public["properties"]) == {
        "id",
        "code",
        "name",
        "service_area",
        "insurance_required",
    }


def test_entry_reference_contract_matches_runtime_target_constraints() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    schemas = document["components"]["schemas"]
    for schema_name in (
        "VolunteerIdentityRequest",
        "VolunteerApplicationCreateRequest",
        "VolunteerApplicationWithdrawRequest",
    ):
        reference = schemas[schema_name]["properties"]["shelter_entry_reference"]
        assert reference["minLength"] == 32
        assert reference["maxLength"] == 512
        assert reference["pattern"] == r"^[A-Za-z0-9._~-]+$"


def test_submit_request_contract_supports_exactly_one_target_and_profile_fields() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    schemas = document["components"]["schemas"]
    schema = schemas["VolunteerApplicationCreateRequest"]
    assert schema["required"] == [
        "id_token",
        "applicant_name",
        "phone_number",
        "client_request_id",
        "consent_acknowledged",
        "service_dates",
    ]
    assert "organization_id" in schema["properties"]
    assert "shelter_entry_reference" in schema["properties"]
    assert len(schema["oneOf"]) == 2
    assert {tuple(branch["required"]) for branch in schema["oneOf"]} == {
        ("organization_id",),
        ("shelter_entry_reference",),
    }
    assert {
        "applicant_name",
        "phone_number",
        "basic_profile",
        "insurance_identity",
        "insurance_consent_acknowledged",
    } <= set(schema["properties"])

    withdraw_schema = schemas["VolunteerApplicationWithdrawRequest"]
    assert withdraw_schema["required"] == [
        "id_token",
        "shelter_entry_reference",
        "expected_version",
    ]
    assert "organization_id" not in withdraw_schema["properties"]
    assert "oneOf" not in withdraw_schema


def test_runtime_openapi_submit_schema_supports_target_and_withdraw_stays_entry_only() -> None:
    schemas = app.openapi()["components"]["schemas"]
    submit_schema = schemas["VolunteerApplicationCreateRequest"]
    assert "organization_id" in submit_schema["properties"]
    assert "applicant_name" in submit_schema["properties"]
    assert len(submit_schema["oneOf"]) == 2

    withdraw_schema = schemas["VolunteerApplicationWithdrawRequest"]
    assert "organization_id" not in withdraw_schema["properties"]
    assert "shelter_entry_reference" in withdraw_schema["required"]
    assert "oneOf" not in withdraw_schema


def test_runtime_openapi_identity_schema_declares_exactly_one_target() -> None:
    schema = app.openapi()["components"]["schemas"]["VolunteerIdentityRequest"]
    assert len(schema["oneOf"]) == 2
    assert {tuple(branch["required"]) for branch in schema["oneOf"]} == {
        ("organization_id",),
        ("shelter_entry_reference",),
    }


def test_submit_model_rejects_missing_or_ambiguous_target() -> None:
    common = {
        "id_token": "synthetic-token",
        "applicant_name": "測試志工",
        "phone_number": "0900000000",
        "client_request_id": "00000000-0000-0000-0000-000000000001",
        "consent_acknowledged": True,
        "service_dates": ["2026-08-15"],
    }
    with pytest.raises(ValidationError):
        VolunteerApplicationCreateRequest.model_validate(common)
    with pytest.raises(ValidationError):
        VolunteerApplicationCreateRequest.model_validate(
            {
                **common,
                "organization_id": "00000000-0000-0000-0000-000000000002",
                "shelter_entry_reference": "A" * 32,
            }
        )


def test_runtime_openapi_volunteer_error_and_nullable_response_schemas_match_contract() -> None:
    document = app.openapi()
    schemas = document["components"]["schemas"]
    status_response = schemas["VolunteerApplicationStatusResponse"]
    assert "application" not in status_response["required"]
    assert "grant" not in status_response["required"]
    public_organization = schemas["PublicOrganizationResponse"]
    assert "insurance_required" in public_organization["required"]
    assert public_organization["properties"]["insurance_required"]["type"] == "boolean"
    assert set(schemas["ErrorResponse"]["required"]) == {"code", "message", "request_id"}
    details = schemas["ErrorResponse"]["properties"]["details"]
    assert details["type"] == "object"
    assert "anyOf" not in details
    application = schemas["VolunteerApplicationResponse"]
    assert "display_name" in application["required"]
    assert application["properties"]["status"]["enum"] == [
        "pending",
        "approved",
        "rejected",
        "withdrawn",
    ]
    assert application["properties"]["version"]["minimum"] == 1
    grant = schemas["VolunteerGrantSummaryResponse"]
    assert grant["properties"]["status"]["enum"] == ["active", "expired", "revoked"]
    assert grant["properties"]["source_type"]["enum"] == [
        "manager_approval",
        "legacy_migration",
    ]
    assert grant["properties"]["version"]["minimum"] == 1
    assert status_response["properties"]["effective_status"]["enum"] == [
        "none",
        "pending",
        "upcoming",
        "active",
        "expired",
        "revoked",
        "rejected",
        "withdrawn",
    ]
    assert status_response["properties"]["next_actions"]["items"]["enum"] == [
        "apply",
        "wait",
        "withdraw",
        "enter_care",
        "reapply",
        "contact_shelter",
        "return_to_line",
    ]
    policy = schemas["VolunteerAccessPolicyResponse"]
    assert policy["properties"]["default_grant_duration_hours"]["minimum"] == 1
    assert policy["properties"]["version"]["minimum"] == 1

    expected_errors = {
        "/v1/volunteer-applications/status": {"401", "403", "422", "503"},
        "/v1/volunteer-applications": {"401", "403", "409", "422", "503"},
        "/v1/volunteer-applications/{applicationId}/withdraw": {
            "401",
            "404",
            "409",
            "422",
            "503",
        },
    }
    for path, codes in expected_errors.items():
        operation = document["paths"][path]["post"]
        assert codes <= operation["responses"].keys()
        for code in codes:
            response = operation["responses"][code]
            assert response["content"]["application/json"]["schema"]["$ref"].endswith(
                "/ErrorResponse"
            )
    submit_responses = document["paths"]["/v1/volunteer-applications"]["post"]["responses"]
    assert {"200", "201"} <= submit_responses.keys()
    assert submit_responses["201"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/VolunteerApplicationStatusResponse"
    )


def test_runtime_openapi_management_volunteer_routes_declare_canonical_responses() -> None:
    paths = app.openapi()["paths"]
    expected = {
        ("/v1/organizations/{organizationId}/volunteer-access-policy", "get"): (
            "VolunteerAccessPolicyResponse",
            {"403", "404"},
        ),
        ("/v1/organizations/{organizationId}/volunteer-access-policy", "patch"): (
            "VolunteerAccessPolicyResponse",
            {"403", "404", "422"},
        ),
        ("/v1/organizations/{organizationId}/volunteer-applications", "get"): (
            "VolunteerApplicationListResponse",
            {"403", "404"},
        ),
        ("/v1/organizations/{organizationId}/volunteer-access-grants", "get"): (
            "VolunteerAccessGrantListResponse",
            {"403", "404"},
        ),
        ("/v1/organizations/{organizationId}/volunteer-notifications/retry", "post"): (
            "VolunteerNotificationRetryResponse",
            {"202", "403", "409", "422"},
        ),
        ("/v1/organizations/{organizationId}/volunteer-decision-batches", "post"): (
            "VolunteerDecisionBatchResponse",
            {"201", "403", "409", "422"},
        ),
    }
    for (path, method), (model_name, error_codes) in expected.items():
        operation = paths[path][method]
        success = operation["responses"]["200" if method == "get" else "200"]
        assert success["content"]["application/json"]["schema"]["$ref"].endswith(f"/{model_name}")
        assert error_codes <= operation["responses"].keys()
        assert {"401", "503"} <= operation["responses"].keys()
        assert operation["security"] == [{"bearerAuth": []}]

    assert app.openapi()["security"] == [{"bearerAuth": []}]
    assert paths["/v1/public/volunteer-organizations"]["get"]["security"] == []
    assert paths["/v1/volunteer-applications/status"]["post"]["security"] == []
    assert paths["/v1/volunteer-applications"]["post"]["security"] == []
    assert paths["/v1/volunteer-applications/{applicationId}/withdraw"]["post"]["security"] == []
    batch_item_operation = paths[
        "/v1/organizations/{organizationId}/volunteer-decision-batches/{batchId}/items"
    ]["get"]
    cursor_parameter = next(
        parameter
        for parameter in batch_item_operation["parameters"]
        if parameter["name"] == "cursor"
    )
    assert cursor_parameter["schema"]["type"] == "string"
    assert app.openapi()["components"]["securitySchemes"]["bearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "RS256 簽署的短效 Access Token；"
            "每次受保護 Request 仍必須通過 Server-side Session 與 Organization Scope 驗證。"
        ),
    }
    grant_schema = app.openapi()["components"]["schemas"]["VolunteerAccessGrant"]
    notification_schema = grant_schema["properties"]["notification"]
    assert notification_schema["anyOf"][0]["$ref"].endswith("/VolunteerNotification")


def test_management_contract_supports_policy_and_resumable_decision_batches() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    paths = document["paths"]
    assert (
        paths["/v1/organizations/{organizationId}/volunteer-access-policy"]["patch"]["operationId"]
        == "updateVolunteerAccessPolicy"
    )
    batch_path = "/v1/organizations/{organizationId}/volunteer-decision-batches"
    assert paths[batch_path]["post"]["operationId"] == "createVolunteerDecisionBatch"
    item_path = batch_path + "/{batchId}/items"
    assert paths[item_path]["get"]["operationId"] == "listVolunteerDecisionBatchItems"
    schemas = document["components"]["schemas"]
    explicit = schemas["ExplicitVolunteerDecisionSelection"]["properties"]["items"]
    assert explicit["minItems"] == 1
    assert explicit["maxItems"] == 500
    assert schemas["AllFilteredVolunteerDecisionSelection"]["properties"]["filter"]


def test_grant_mutation_contract_has_discriminator_version_and_immediate_confirmation() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    path = document["paths"][
        "/v1/organizations/{organizationId}/volunteer-access-grants/{grantId}"
    ]["patch"]
    assert path["operationId"] == "updateVolunteerAccessGrant"
    assert set(GrantPeriodUpdateRequest.model_fields) == {
        "action",
        "expected_version",
        "valid_from",
        "expires_at",
        "confirm_immediate_expiry",
        "reason",
    }
    assert set(GrantRevokeRequest.model_fields) == {
        "action",
        "expected_version",
        "reason",
    }


def test_notification_failure_list_and_retry_contract_are_registered() -> None:
    routes = {
        (route.path, method)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
    }
    assert ("/v1/organizations/{organizationId}/volunteer-notifications", "GET") in routes
    assert (
        "/v1/organizations/{organizationId}/volunteer-notifications/retry",
        "POST",
    ) in routes
    field = VolunteerNotificationRetryRequest.model_fields["notification_ids"]
    assert field.is_required()
