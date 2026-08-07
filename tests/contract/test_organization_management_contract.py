from pathlib import Path

import yaml
from fastapi.routing import APIRoute
from services.api.app.api.organization_management import (
    AccountCreateRequest,
    OrganizationCreateRequest,
    router,
)


def test_organization_management_contract_declares_memberships_areas_and_isolation_fields():
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    paths = document["paths"]
    assert "/v1/organizations/{organizationId}/memberships" in paths
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
