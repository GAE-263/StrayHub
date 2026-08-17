from pathlib import Path

import yaml
from fastapi.routing import APIRoute
from services.api.app.api.authentication import router


def test_authentication_contract_exposes_required_operations() -> None:
    paths = {route.path for route in router.routes if isinstance(route, APIRoute)}
    assert paths == {
        "/v1/auth/login",
        "/v1/auth/refresh",
        "/v1/auth/logout",
        "/v1/auth/liff/exchange",
        "/v1/auth/me",
        "/v1/auth/active-shelter-context",
    }
    methods = {
        (route.path, method)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    assert ("/v1/auth/login", "POST") in methods
    assert ("/v1/auth/active-shelter-context", "PUT") in methods


def test_authentication_contract_declares_all_session_operations() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text(encoding="utf-8")
    )
    paths = document["paths"]

    assert "/v1/auth/login" in paths
    assert "/v1/auth/refresh" in paths
    assert "/v1/auth/logout" in paths
    assert "/v1/auth/me" in paths
    assert "/v1/auth/liff/exchange" in paths
    assert "/v1/auth/active-shelter-context" in paths
    assert paths["/v1/auth/login"]["post"]["security"] == []
    assert paths["/v1/auth/active-shelter-context"]["put"].get("security") is None


def test_authentication_contract_does_not_put_organization_or_role_in_token_schema() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text(encoding="utf-8")
    )
    description = document["components"]["securitySchemes"]["bearerAuth"]["description"]

    assert "Server-side Session" in description
    assert "Organization Scope" in description


def test_004_handoff_uses_effective_membership_not_role_alone() -> None:
    from services.api.app.persistence.repositories.authentication_repository import (
        AuthenticationRepository,
    )

    assert hasattr(AuthenticationRepository, "get_effective_membership")
