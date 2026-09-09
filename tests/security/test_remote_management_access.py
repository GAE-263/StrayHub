from uuid import uuid4

import pytest
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.api.management_access import (
    enforce_public_management_role,
    enforce_session_exposure_profile,
    require_management_context,
    resolve_public_exposure_profile,
)
from starlette.requests import Request


def request(*, host: str, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/auth/me",
            "headers": headers or [],
            "client": (host, 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


def test_public_profile_is_only_accepted_from_configured_loopback_gateway() -> None:
    assert (
        resolve_public_exposure_profile(
            request(
                host="127.0.0.1",
                headers=[(b"x-strayhub-public-profile", b"shared-demo-production")],
            ),
            trusted_proxy_enabled=True,
        )
        == "shared-demo-production"
    )
    for forged in (
        request(
            host="198.51.100.8",
            headers=[(b"x-strayhub-public-profile", b"shared-demo-production")],
        ),
        request(
            host="127.0.0.1",
            headers=[
                (b"x-strayhub-public-profile", b"shared-demo-production"),
                (b"x-strayhub-public-profile", b"shared-demo-dev"),
            ],
        ),
    ):
        with pytest.raises(ValueError, match="public exposure profile unavailable"):
            resolve_public_exposure_profile(forged, trusted_proxy_enabled=True)


def test_remote_session_cannot_be_replayed_outside_its_trusted_profile() -> None:
    enforce_session_exposure_profile(
        session_origin="remote_management_demo",
        persisted_profile="shared-demo-production",
        request_profile="shared-demo-production",
    )
    for request_profile in (None, "shared-demo-dev"):
        with pytest.raises(DomainError) as caught:
            enforce_session_exposure_profile(
                session_origin="remote_management_demo",
                persisted_profile="shared-demo-production",
                request_profile=request_profile,
            )
        assert (caught.value.status_code, caught.value.code) == (401, "invalid_session")


def test_local_session_is_not_reclassified_by_public_request_metadata() -> None:
    enforce_session_exposure_profile(
        session_origin="local_web",
        persisted_profile=None,
        request_profile="shared-demo-production",
    )


@pytest.mark.parametrize("role", ["PLATFORM_ADMIN", "VOLUNTEER", ""])
def test_shared_profile_rejects_non_management_demo_roles(role: str) -> None:
    context = RequestContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        membership_id=uuid4(),
        role=role,
        platform_scope=role == "PLATFORM_ADMIN",
        public_exposure_profile="shared-demo-production",
    )
    with pytest.raises(DomainError) as caught:
        require_management_context(context)
    assert (caught.value.status_code, caught.value.code) == (403, "management_access_denied")
    with pytest.raises(DomainError):
        enforce_public_management_role(context)


@pytest.mark.parametrize("role", ["STAFF", "SHELTER_ADMIN"])
def test_shared_profile_allows_active_management_roles(role: str) -> None:
    organization_id = uuid4()
    context = RequestContext(
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        role=role,
        public_exposure_profile="shared-demo-dev",
    )
    assert require_management_context(context) == organization_id


def test_local_platform_admin_behavior_is_unchanged() -> None:
    organization_id = uuid4()
    context = RequestContext(
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=None,
        role="PLATFORM_ADMIN",
        platform_scope=True,
    )
    assert require_management_context(context) == organization_id
