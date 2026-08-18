from pathlib import Path

import yaml
from fastapi.routing import APIRoute
from services.api.app.api.platform_admin_management import (
    CreatePlatformAdminRequest,
    PlatformAdminResponse,
    router,
)


def test_platform_admin_router_exposes_global_operations_without_shelter_context():
    routes = {
        (route.path, method.upper())
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
    }
    assert ("/v1/platform/administrators", "GET") in routes
    assert ("/v1/platform/administrators", "POST") in routes
    assert ("/v1/platform/administrators/replacements", "POST") in routes
    assert ("/v1/platform/administrators/audit", "GET") in routes
    assert ("/v1/platform/administrators/{userId}/enable", "POST") in routes
    assert ("/v1/platform/administrators/{userId}/disable", "POST") in routes
    assert ("/v1/platform/administrators/{userId}/demote", "POST") in routes


def test_platform_admin_contract_is_present_in_openapi_source():
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    assert "/v1/platform/administrators" in document["paths"]
    assert "/v1/platform/administrators/replacements" in document["paths"]
    assert "PlatformAdminListResponse" in document["components"]["schemas"]
    assert "platform_admin_required" not in CreatePlatformAdminRequest.model_fields


def test_platform_admin_projection_exposes_identity_and_safe_action_flags():
    assert {
        "user_id",
        "username",
        "display_name",
        "effective_status",
        "can_enable",
        "can_disable",
        "can_demote",
    } <= PlatformAdminResponse.model_fields.keys()


def test_platform_admin_action_payloads_do_not_accept_organization_id():
    assert "organization_id" not in CreatePlatformAdminRequest.model_fields
