from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import yaml
from fastapi.routing import APIRoute
from services.api.app.api.organization_management import (
    AccountCreateRequest,
    MembershipResponse,
    OrganizationCreateRequest,
    OrganizationUpdateRequest,
    ShelterAreaCreateRequest,
    _membership_response,
    router,
)


def test_organization_management_contract_declares_memberships_areas_and_isolation_fields():
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    paths = document["paths"]
    assert "/v1/organizations/{organizationId}/memberships" in paths
    assert "/v1/organizations/{organizationId}/memberships/archived" in paths
    assert "/v1/organizations/{organizationId}/memberships/{membershipId}/archive" in paths
    assert "/v1/organizations/{organizationId}/memberships/{membershipId}/restore" in paths
    assert "/v1/organizations/{organizationId}/accounts" in paths
    assert "/v1/organizations/{organizationId}/areas" in paths
    assert "organization_id" in document["components"]["schemas"]["ShelterArea"]["properties"]
    create_properties = document["components"]["schemas"]["ShelterAreaCreateRequest"].get(
        "properties", {}
    )
    assert "organization_id" not in create_properties


def test_organization_creation_requires_pending_status_and_initial_admin_credentials():
    fields = OrganizationCreateRequest.model_fields
    assert fields["status"].is_required()
    assert fields["initial_admin_username"].is_required()
    assert fields["initial_admin_temporary_password"].is_required()
    assert AccountCreateRequest.model_fields["role"].is_required()


def test_organization_mutation_payloads_never_accept_client_organization_id():
    for model in (
        OrganizationCreateRequest,
        OrganizationUpdateRequest,
        AccountCreateRequest,
        ShelterAreaCreateRequest,
    ):
        assert "organization_id" not in model.model_fields


def test_organization_router_exposes_account_area_status_and_initial_admin_operations():
    routes = {
        (route.path, method.upper())
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
    }
    assert ("/v1/organizations", "POST") in routes
    assert ("/v1/organizations/{organizationId}/accounts", "POST") in routes
    assert ("/v1/organizations/{organizationId}/areas", "POST") in routes
    assert ("/v1/organizations/{organizationId}/initial-admin", "POST") in routes
    assert ("/v1/organizations/{organizationId}", "PATCH") in routes


def test_membership_contract_exposes_finite_volunteer_projection() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    properties = document["components"]["schemas"]["Membership"]["properties"]
    assert {"valid_from", "expires_at", "access_version"} <= properties.keys()
    assert {"username", "display_name"} <= properties.keys()
    assert {"archived_from_status", "archived_at", "archived_by_user_id"} <= properties.keys()
    assert "archived" in properties["status"]["enum"]
    assert {"valid_from", "expires_at", "access_version"} <= MembershipResponse.model_fields.keys()


def test_membership_response_includes_user_identity_projection() -> None:
    response = _membership_response(
        SimpleNamespace(
            id=uuid4(),
            organization_id=uuid4(),
            user_id=uuid4(),
            role="STAFF",
            status="active",
            valid_from=None,
            expires_at=None,
            access_version=1,
            medical_care_access=False,
        ),
        SimpleNamespace(username="local-staff-a", display_name="本機工作人員 A"),
    )

    assert response.username == "local-staff-a"
    assert response.display_name == "本機工作人員 A"


def test_organization_router_exposes_membership_archive_lifecycle_operations():
    routes = {
        (route.path, method.upper())
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
    }
    assert ("/v1/organizations/{organizationId}/memberships/archived", "GET") in routes
    assert (
        "/v1/organizations/{organizationId}/memberships/{membershipId}/archive",
        "POST",
    ) in routes
    assert (
        "/v1/organizations/{organizationId}/memberships/{membershipId}/restore",
        "POST",
    ) in routes


def test_auth_contract_distinguishes_platform_role_from_shelter_membership_role() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    user_role = document["components"]["schemas"]["User"]["properties"]["roles"]
    assert "PLATFORM_ADMIN" in user_role["items"]["enum"]
    login_role = document["components"]["schemas"]["LoginOrganization"]["properties"]["role"]
    assert "PLATFORM_ADMIN" not in login_role["enum"]
    access_scope = document["components"]["schemas"]["AccessScope"]["properties"]["type"]
    assert {"PLATFORM", "SHELTER"} <= set(access_scope["enum"])
