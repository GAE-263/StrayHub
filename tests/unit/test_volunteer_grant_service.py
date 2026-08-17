from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from services.api.app.application.volunteer_access_service import (
    effective_application_status,
    grant_remaining_seconds,
)

NOW = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)


def test_grant_effective_status_obeys_exact_boundaries_and_remaining_duration() -> None:
    application = SimpleNamespace(status="approved")
    upcoming = SimpleNamespace(
        status="active",
        valid_from=NOW + timedelta(hours=1),
        expires_at=NOW + timedelta(hours=3),
    )
    assert effective_application_status(application, upcoming, now=NOW)[0] == "upcoming"
    assert grant_remaining_seconds(upcoming, now=NOW) == 3 * 60 * 60
    assert effective_application_status(application, upcoming, now=upcoming.valid_from)[0] == (
        "active"
    )
    assert effective_application_status(application, upcoming, now=upcoming.expires_at)[0] == (
        "expired"
    )
    assert grant_remaining_seconds(upcoming, now=upcoming.expires_at) == 0


def test_revoked_grant_never_becomes_effective() -> None:
    application = SimpleNamespace(status="approved")
    grant = SimpleNamespace(
        status="revoked",
        valid_from=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
    )
    assert effective_application_status(application, grant, now=NOW)[0] == "revoked"
