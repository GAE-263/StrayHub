import pytest
from services.api.app.infrastructure.line.identity_verification_adapter import (
    MockLineIdentityVerifier,
    configured_line_identity_verifier,
)


@pytest.mark.asyncio
async def test_local_mock_line_identity_maps_deterministic_token() -> None:
    verifier = MockLineIdentityVerifier()

    assert await verifier.verify("local-id-token:local-volunteer-A") == ("Ulocal-volunteer-A")
    assert await verifier.verify("local-id-token:Ulocal-volunteer-A") == ("Ulocal-volunteer-A")


def test_fake_line_configuration_uses_mock_only_in_local() -> None:
    assert isinstance(
        configured_line_identity_verifier(app_env="local", channel_id="fake-line-channel-id"),
        MockLineIdentityVerifier,
    )
    assert (
        configured_line_identity_verifier(
            app_env="production", channel_id="fake-line-channel-id"
        ).__class__.__name__
        == "LineIdentityVerifier"
    )
