from pathlib import Path
from uuid import uuid4

import pytest
import yaml  # type: ignore[import-untyped]
from fastapi.routing import APIRoute
from pydantic import TypeAdapter, ValidationError
from services.api.app.api.authentication import (
    CurrentUserResponse,
    LiffExchangeResponse,
    RefreshRequest,
    current_user,
    refresh,
    router,
)
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from starlette.requests import Request


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


def test_current_user_route_serves_membership_grant_validity_schema() -> None:
    route = next(route for route in router.routes if route.path == "/v1/auth/me")

    assert route.response_model is CurrentUserResponse


def test_current_user_contract_has_server_derived_nullable_exposure_hint() -> None:
    schema = CurrentUserResponse.model_json_schema()
    assert "public_exposure_profile" in schema["properties"]
    assert schema["properties"]["public_exposure_profile"]["default"] is None

    with pytest.raises(ValidationError):
        RefreshRequest.model_validate(
            {
                "refresh_token": "body-token",
                "public_exposure_profile": "shared-demo-production",
            }
        )


@pytest.mark.asyncio
async def test_refresh_commits_security_revocation_before_returning_error() -> None:
    class Service:
        async def refresh(self, *, refresh_token, public_exposure_profile=None):
            raise DomainError("invalid_session", "Session 無效", 401)

    class Session:
        commits = 0

        async def commit(self):
            self.commits += 1

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/auth/refresh",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    session = Session()
    with pytest.raises(DomainError, match="Session 無效"):
        await refresh(
            request=request,
            payload=RefreshRequest(refresh_token="a" * 64),
            service=Service(),
            session=session,
        )
    assert session.commits == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (None, None),
        ("shared-demo-production", "shared-demo-production"),
        ("shared-demo-dev", "shared-demo-dev"),
    ],
)
async def test_current_user_hint_comes_from_request_context(profile, expected) -> None:
    session_id = uuid4()

    class Service:
        async def current_user(self, *, session_id, public_exposure_profile=None):
            return {
                "user": {
                    "id": uuid4(),
                    "username": "staff",
                    "display_name": "Staff",
                    "platform_role": None,
                    "status": "active",
                },
                "memberships": [],
                "public_exposure_profile": public_exposure_profile,
            }

    response = await current_user(
        context=RequestContext(
            user_id=uuid4(),
            organization_id=uuid4(),
            membership_id=uuid4(),
            role="STAFF",
            session_id=session_id,
            public_exposure_profile=profile,
        ),
        service=Service(),
    )
    assert response.public_exposure_profile == expected


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


def test_active_shelter_context_contract_includes_server_confirmed_name() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text(encoding="utf-8")
    )
    schema = document["components"]["schemas"]["ActiveShelterContext"]

    assert "organization_name" in schema["required"]
    assert schema["properties"]["organization_name"] == {"type": "string"}


def test_current_user_contract_exposes_volunteer_grant_validity_evidence() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text(encoding="utf-8")
    )
    membership = document["components"]["schemas"]["CurrentUserMembership"]
    grant = document["components"]["schemas"]["CurrentUserAccessGrant"]

    assert {"valid_from", "expires_at", "access_grant"} <= membership["properties"].keys()
    assert membership["properties"]["access_grant"]["oneOf"][1] == {"type": "null"}
    assert {
        "membership_id",
        "organization_id",
        "status",
        "valid_from",
        "expires_at",
    } <= set(grant["required"])


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

    assert hasattr(AuthenticationRepository, "get_effective_volunteer_membership")
    assert hasattr(AuthenticationRepository, "lock_effective_volunteer_access")


def test_liff_exchange_requires_only_raw_identity_and_opaque_entry() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text(encoding="utf-8")
    )
    schema = document["components"]["schemas"]["LiffExchangeRequest"]
    assert set(schema["required"]) == {"id_token", "shelter_entry_reference"}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["shelter_entry_reference"]["minLength"] == 32


def test_runtime_liff_response_models_isolate_active_credentials() -> None:
    organization = {"id": uuid4(), "code": "ORG-A", "name": "收容所 A"}
    adapter = TypeAdapter(LiffExchangeResponse)

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "state": "NEW",
                "organization": organization,
                "next_path": "/volunteer-application",
                "access_token": "must-not-be-present",
            }
        )

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "state": "ACTIVE",
                "organization": organization,
                "next_path": "/animal-confirmation",
                "user": {"role": "VOLUNTEER"},
            }
        )

    validated = adapter.validate_python(
        {
            "state": "ACTIVE",
            "organization": organization,
            "next_path": "/animal-confirmation",
            "user": {"role": "VOLUNTEER"},
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 900,
            "session_id": uuid4(),
            "user_id": uuid4(),
        }
    )
    assert validated.state == "ACTIVE"
