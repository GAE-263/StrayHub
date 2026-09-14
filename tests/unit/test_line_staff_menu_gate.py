"""Staff LINE menu gate tests use synthetic identities and mocked transports only."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from unittest.mock import AsyncMock, Mock

import pytest
from services.api.app.config.line_menu_smoke import verified_menu_request
from services.api.app.config.settings import Settings

UID = "U" + "1" * 32
OTHER_UID = "U" + "3" * 32
BOT = "U" + "2" * 32


def scoped_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "app_env": "production",
        "line_channel_id": "1234567890",
        "line_role_menu_test_enabled": True,
        "line_role_menu_test_channel_id": "1234567890",
        "line_role_menu_bot_sha256": sha256(BOT.encode()).hexdigest(),
        "line_role_menu_test_user_sha256": sha256(UID.encode()).hexdigest(),
        "line_role_menu_test_expires_at": (
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).isoformat(),
    }
    values.update(overrides)
    return Settings(**values)


def test_staff_scope_truth_table_and_expiry() -> None:
    settings = scoped_settings()
    assert not settings.line_staff_menu_allowed(UID)

    settings.line_staff_menu_enabled = True
    assert settings.line_staff_menu_allowed(UID)
    assert not settings.line_staff_menu_allowed(OTHER_UID)
    assert not settings.line_staff_menu_allowed(None)

    settings.line_role_menu_test_expires_at = "2020-01-01T00:00:00+00:00"
    assert not settings.line_staff_menu_allowed(UID)
    settings.line_role_menu_test_enabled = False
    assert not settings.line_staff_menu_allowed(UID)


@pytest.mark.asyncio
async def test_scoped_staff_action_requires_opt_in_and_verified_webhook(monkeypatch) -> None:
    from services.api.app.api import line_webhook
    from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter

    settings = scoped_settings(line_staff_menu_enabled=True)
    monkeypatch.setattr(line_webhook, "get_settings", lambda: settings)
    event = {
        "type": "postback",
        "replyToken": "synthetic",
        "source": {"type": "user", "userId": UID},
        "postback": {"data": "action=staff_create_animal"},
    }

    unverified = MockLineAdapter()
    assert await line_webhook._handle_menu_action(unverified, event)
    assert unverified.replies[0][1][0]["text"] == "此 LINE 功能目前尚未開放。"

    verified = MockLineAdapter()
    async with verified_menu_request({"destination": BOT, "events": [event]}, settings):
        assert not await line_webhook._handle_menu_action(verified, event)
    assert verified.replies == []

    settings.line_staff_menu_enabled = False
    disabled = MockLineAdapter()
    async with verified_menu_request({"destination": BOT, "events": [event]}, settings):
        assert await line_webhook._handle_menu_action(disabled, event)
    assert disabled.replies[0][1][0]["text"] == "此 LINE 功能目前尚未開放。"


@pytest.mark.asyncio
async def test_webhook_staff_gate_delegates_verified_user_to_authoritative_helper(
    monkeypatch,
) -> None:
    from services.api.app.api import line_webhook
    from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter

    settings = scoped_settings(line_staff_menu_enabled=True)
    staff_allowed = Mock(return_value=False)
    role_gate = Mock(side_effect=AssertionError("Staff gate must not recompose role rollout"))
    monkeypatch.setattr(Settings, "line_staff_menu_allowed", staff_allowed)
    monkeypatch.setattr(line_webhook, "get_settings", lambda: settings)
    monkeypatch.setattr(line_webhook, "_line_role_menu_features_active", role_gate)
    business_handler = AsyncMock()
    monkeypatch.setattr(line_webhook, "_handle_staff_menu_action", business_handler)
    event = {
        "type": "postback",
        "replyToken": "synthetic",
        "source": {"type": "user", "userId": UID},
        "postback": {"data": "action=staff_create_animal"},
    }

    line = MockLineAdapter()
    async with verified_menu_request({"destination": BOT, "events": [event]}, settings):
        assert await line_webhook._handle_menu_action(line, event)

    staff_allowed.assert_called_once_with(UID)
    role_gate.assert_not_called()
    business_handler.assert_not_awaited()
    assert line.replies[0][1][0]["text"] == "此 LINE 功能目前尚未開放。"


@pytest.mark.asyncio
async def test_webhook_staff_gate_allows_existing_staff_authorization_after_delegation(
    monkeypatch,
) -> None:
    from services.api.app.api import line_webhook
    from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter

    settings = scoped_settings(line_staff_menu_enabled=True)
    staff_allowed = Mock(return_value=True)
    monkeypatch.setattr(Settings, "line_staff_menu_allowed", staff_allowed)
    monkeypatch.setattr(line_webhook, "get_settings", lambda: settings)
    event = {
        "type": "postback",
        "replyToken": "synthetic",
        "source": {"type": "user", "userId": UID},
        "postback": {"data": "action=staff_create_animal"},
    }

    line = MockLineAdapter()
    async with verified_menu_request({"destination": BOT, "events": [event]}, settings):
        assert not await line_webhook._handle_menu_action(line, event)

    staff_allowed.assert_called_once_with(UID)
    assert line.replies == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source",
    [
        {"type": "user", "userId": UID},
        {"type": "group", "userId": UID, "groupId": "synthetic-group"},
        {"type": "room", "userId": UID, "roomId": "synthetic-room"},
    ],
)
async def test_webhook_staff_gate_does_not_delegate_unverified_or_non_user_source(
    monkeypatch,
    source,
) -> None:
    from services.api.app.api import line_webhook
    from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter

    settings = scoped_settings(line_staff_menu_enabled=True)
    staff_allowed = Mock(return_value=True)
    monkeypatch.setattr(Settings, "line_staff_menu_allowed", staff_allowed)
    monkeypatch.setattr(line_webhook, "get_settings", lambda: settings)
    event = {
        "type": "postback",
        "replyToken": "synthetic",
        "source": source,
        "postback": {"data": "action=staff_create_animal"},
    }

    line = MockLineAdapter()
    assert await line_webhook._handle_menu_action(line, event)

    staff_allowed.assert_not_called()
    assert line.replies[0][1][0]["text"] == "此 LINE 功能目前尚未開放。"


@pytest.mark.asyncio
async def test_legacy_worker_uses_combined_staff_scope(monkeypatch) -> None:
    from services.worker.app.handlers import volunteer_access_handler as worker

    settings = scoped_settings(
        line_staff_menu_enabled=True,
        line_rich_menu_default_id="richmenu-default",
        line_rich_menu_staff_id="richmenu-staff",
    )
    line = AsyncMock()
    monkeypatch.setattr(worker, "get_worker_settings", lambda: settings)
    monkeypatch.setattr(worker, "LineMessagingApiAdapter", lambda **kwargs: line)

    router = worker._rich_menu_router()

    assert router is not None
    assert (
        await router.link_for_user(line_user_id=UID, role="STAFF", organization_selected=True)
        == "richmenu-staff"
    )
    assert (
        await router.link_for_user(
            line_user_id=OTHER_UID,
            role="STAFF",
            organization_selected=True,
        )
        is None
    )
    line.link_rich_menu.assert_awaited_once_with(rich_menu_id="richmenu-staff", user_id=UID)


@pytest.mark.asyncio
async def test_legacy_worker_omits_staged_staff_menu_while_disabled(monkeypatch) -> None:
    from services.worker.app.handlers import volunteer_access_handler as worker

    settings = scoped_settings(
        line_staff_menu_enabled=False,
        line_rich_menu_default_id="richmenu-default",
        line_rich_menu_staff_id="richmenu-staged-staff",
    )
    line = AsyncMock()
    monkeypatch.setattr(worker, "get_worker_settings", lambda: settings)
    monkeypatch.setattr(worker, "LineMessagingApiAdapter", lambda **kwargs: line)

    router = worker._rich_menu_router()

    assert router is not None
    assert (
        await router.link_for_user(line_user_id=UID, role="STAFF", organization_selected=True)
        is None
    )
    line.link_rich_menu.assert_not_awaited()


def test_authentication_router_uses_combined_staff_scope(monkeypatch) -> None:
    from services.api.app.api import authentication
    from services.api.app.infrastructure.line import messaging_api_adapter

    settings = scoped_settings(
        line_staff_menu_enabled=True,
        line_rich_menu_default_id="richmenu-default",
        line_rich_menu_staff_id="richmenu-staff",
        auth_jwt_active_private_key="synthetic-private-key",
        auth_jwt_active_public_key="synthetic-public-key",
        login_abuse_hmac_secret="synthetic-login-abuse-key",
    )
    line = AsyncMock()
    monkeypatch.setattr(authentication, "get_settings", lambda: settings)
    monkeypatch.setattr(authentication, "Argon2PasswordHasher", lambda: object())
    monkeypatch.setattr(authentication, "JwtAccessTokenAdapter", lambda **kwargs: object())
    monkeypatch.setattr(
        authentication, "configured_line_identity_verifier", lambda **kwargs: object()
    )
    monkeypatch.setattr(messaging_api_adapter, "LineMessagingApiAdapter", lambda: line)

    router = authentication.get_session_service(object()).rich_menu_router

    assert router is not None
    assert router.staff_allowed is not None
    assert router.staff_allowed(UID)
    assert not router.staff_allowed(OTHER_UID)


def test_authentication_router_omits_staged_staff_menu_while_disabled(monkeypatch) -> None:
    from services.api.app.api import authentication
    from services.api.app.infrastructure.line import messaging_api_adapter

    settings = scoped_settings(
        line_staff_menu_enabled=False,
        line_rich_menu_default_id="richmenu-default",
        line_rich_menu_staff_id="richmenu-staged-staff",
        auth_jwt_active_private_key="synthetic-private-key",
        auth_jwt_active_public_key="synthetic-public-key",
        login_abuse_hmac_secret="synthetic-login-abuse-key",
    )
    monkeypatch.setattr(authentication, "get_settings", lambda: settings)
    monkeypatch.setattr(authentication, "Argon2PasswordHasher", lambda: object())
    monkeypatch.setattr(authentication, "JwtAccessTokenAdapter", lambda **kwargs: object())
    monkeypatch.setattr(
        authentication, "configured_line_identity_verifier", lambda **kwargs: object()
    )
    monkeypatch.setattr(messaging_api_adapter, "LineMessagingApiAdapter", lambda: AsyncMock())

    router = authentication.get_session_service(object()).rich_menu_router

    assert router is not None
    assert router.registry.get("staff") is None
    assert router.registry.get("default") == "richmenu-default"
