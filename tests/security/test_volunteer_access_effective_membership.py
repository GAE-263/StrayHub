from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from services.api.app.domain.volunteer_access import is_effective_volunteer_membership

NOW = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)


def _record(**overrides):
    values = {
        "role": "VOLUNTEER",
        "status": "active",
        "valid_from": NOW - timedelta(hours=1),
        "expires_at": NOW + timedelta(hours=1),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_effective_membership_requires_active_user_org_membership_and_grant() -> None:
    membership = _record()
    grant = SimpleNamespace(status="active")
    assert is_effective_volunteer_membership(
        membership,
        grant,
        now=NOW,
        organization_status="active",
        user_status="active",
    )
    for kwargs in (
        {"organization_status": "suspended", "user_status": "active"},
        {"organization_status": "active", "user_status": "disabled"},
    ):
        assert not is_effective_volunteer_membership(membership, grant, now=NOW, **kwargs)


def test_effective_membership_uses_exact_half_open_boundary() -> None:
    grant = SimpleNamespace(status="active")
    assert not is_effective_volunteer_membership(
        _record(valid_from=NOW + timedelta(seconds=1)), grant, now=NOW
    )
    assert not is_effective_volunteer_membership(_record(expires_at=NOW), grant, now=NOW)
    assert not is_effective_volunteer_membership(_record(status="revoked"), grant, now=NOW)
    assert not is_effective_volunteer_membership(
        _record(), SimpleNamespace(status="revoked"), now=NOW
    )


def test_non_volunteer_management_role_does_not_require_grant_period() -> None:
    assert is_effective_volunteer_membership(
        _record(role="SHELTER_ADMIN", valid_from=None, expires_at=None),
        None,
        now=NOW,
    )
