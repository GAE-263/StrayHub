from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.reportable_scope_service import (
    can_report,
    require_reportable_scope,
    scope_is_current,
)


def test_reportable_scope_requires_active_animal_and_current_scope() -> None:
    organization_id = uuid4()
    assert can_report(
        organization_id=organization_id,
        animal_organization_id=organization_id,
        animal_status="active",
        scope_active=True,
    )
    assert not can_report(
        organization_id=organization_id,
        animal_organization_id=organization_id,
        animal_status="archived",
        scope_active=True,
    )
    assert not can_report(
        organization_id=organization_id,
        animal_organization_id=organization_id,
        animal_status="active",
        scope_active=False,
    )


def test_reportable_scope_rejects_cross_org_animal() -> None:
    with pytest.raises(DomainError, match="其他收容所"):
        can_report(
            organization_id=uuid4(),
            animal_organization_id=uuid4(),
            animal_status="active",
            scope_active=True,
        )


def test_scope_time_boundaries_are_inclusive() -> None:
    current = datetime.now(timezone.utc)
    assert scope_is_current(starts_at=current, ends_at=current, now=current)
    assert not scope_is_current(
        starts_at=current - timedelta(hours=2),
        ends_at=current - timedelta(hours=1),
        now=current,
    )


@pytest.mark.asyncio
async def test_missing_reportable_scope_blocks_draft_entry() -> None:
    class Repository:
        async def is_animal_reportable(self, **_kwargs):
            return False

    with pytest.raises(DomainError, match="今日可回報範圍"):
        await require_reportable_scope(Repository(), animal_id=uuid4(), volunteer_user_id=uuid4())
