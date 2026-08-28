from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.volunteer_expiration_service import (
    VolunteerExpirationService,
)


@pytest.mark.asyncio
async def test_expiration_sweep_is_idempotent_and_clears_only_target_context() -> None:
    now = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)
    organization_id = uuid4()
    membership = SimpleNamespace(id=uuid4(), status="active", access_version=1)
    grant = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        user_id=uuid4(),
        membership_id=membership.id,
        status="active",
        valid_from=now - timedelta(days=7),
        expires_at=now,
        version=1,
    )

    class Repository:
        def __init__(self):
            self.organization_id = organization_id

        async def due_or_invalid_grants(self, **_kwargs):
            return [grant] if grant.status == "active" else []

    class Identities:
        def __init__(self):
            self.cleared = []

        async def get_membership(self, *_args):
            return membership

        async def clear_volunteer_contexts(self, user_id, target):
            self.cleared.append((user_id, target))

        async def get_line_binding_for_user(self, _user_id):
            return None

    identities = Identities()
    service = VolunteerExpirationService(Repository(), identities)
    assert await service.sweep(now=now) == 1
    assert await service.sweep(now=now) == 0
    assert grant.status == "expired"
    assert membership.status == "disabled"
    assert identities.cleared == [(grant.user_id, organization_id)]


def _expiring_fixtures(now: datetime):
    organization_id = uuid4()
    membership = SimpleNamespace(id=uuid4(), status="active", access_version=1)
    grant = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        user_id=uuid4(),
        membership_id=membership.id,
        status="active",
        valid_from=now - timedelta(days=7),
        expires_at=now,
        version=1,
    )

    class Repository:
        def __init__(self):
            self.organization_id = organization_id

        async def due_or_invalid_grants(self, **_kwargs):
            return [grant] if grant.status == "active" else []

    class Identities:
        def __init__(self, binding=None):
            self.cleared = []
            self.binding = binding

        async def get_membership(self, *_args):
            return membership

        async def clear_volunteer_contexts(self, user_id, target):
            self.cleared.append((user_id, target))

        async def get_line_binding_for_user(self, _user_id):
            return self.binding

    return Repository, Identities, grant, membership


class RecordingRouter:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.fail = fail

    async def link_for_user(self, *, line_user_id: str, role: str | None):
        self.calls.append((line_user_id, role))
        if self.fail:
            raise RuntimeError("LINE API 不可用")
        return "richmenu-default"


@pytest.mark.asyncio
async def test_expiry_resets_rich_menu_to_default() -> None:
    """Rich Menu 是 push 的；到期不重連的話使用者會一直停在志工選單。"""
    now = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)
    Repository, Identities, grant, _ = _expiring_fixtures(now)
    identities = Identities(binding=SimpleNamespace(id=uuid4(), line_user_id="U-expired"))
    router = RecordingRouter()

    changed = await VolunteerExpirationService(
        Repository(), identities, rich_menu_router=router
    ).sweep(now=now)

    assert changed == 1
    assert router.calls == [("U-expired", None)]


@pytest.mark.asyncio
async def test_expiry_without_line_binding_skips_menu_reset() -> None:
    now = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)
    Repository, Identities, _, _ = _expiring_fixtures(now)
    router = RecordingRouter()

    changed = await VolunteerExpirationService(
        Repository(), Identities(binding=None), rich_menu_router=router
    ).sweep(now=now)

    assert changed == 1
    assert router.calls == []


@pytest.mark.asyncio
async def test_menu_reset_failure_does_not_abort_the_sweep() -> None:
    """權限收斂才是重點；LINE 掛掉不該讓整批到期處理失敗。"""
    now = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)
    Repository, Identities, grant, membership = _expiring_fixtures(now)
    identities = Identities(binding=SimpleNamespace(id=uuid4(), line_user_id="U-expired"))

    changed = await VolunteerExpirationService(
        Repository(), identities, rich_menu_router=RecordingRouter(fail=True)
    ).sweep(now=now)

    assert changed == 1
    assert grant.status == "expired"
    assert membership.status == "disabled"
