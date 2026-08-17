from pathlib import Path

import yaml
from fastapi.routing import APIRoute
from services.api.app.api.volunteer_access import (
    GrantPeriodUpdateRequest,
    GrantRevokeRequest,
    VolunteerApplicationCreateRequest,
    VolunteerApplicationWithdrawRequest,
    VolunteerIdentityRequest,
    VolunteerNotificationRetryRequest,
    router,
)


def test_application_contract_declares_status_submit_withdraw_and_safe_errors() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    paths = document["paths"]
    assert paths["/v1/volunteer-applications/status"]["post"]["operationId"] == (
        "resolveVolunteerApplicationStatus"
    )
    submit = paths["/v1/volunteer-applications"]["post"]
    assert {"200", "201", "403", "409", "422", "503"} <= submit["responses"].keys()
    withdraw = paths["/v1/volunteer-applications/{applicationId}/withdraw"]["post"]
    assert {"200", "404", "409", "422"} <= withdraw["responses"].keys()


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
        "shelter_entry_reference",
    }
    assert VolunteerApplicationCreateRequest.model_fields["consent_acknowledged"].is_required()
    assert VolunteerApplicationWithdrawRequest.model_fields["expected_version"].is_required()


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
