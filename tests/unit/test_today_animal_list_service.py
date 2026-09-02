from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.animal_selection import TodayAnimalListService


@pytest.mark.asyncio
async def test_today_list_groups_count_and_latest_without_disabling_reported_animals() -> None:
    organization_id = uuid4()
    first = SimpleNamespace(id=uuid4(), organization_id=organization_id, status="active")
    second = SimpleNamespace(id=uuid4(), organization_id=organization_id, status="active")
    latest = datetime(2026, 9, 1, 15, 59, tzinfo=timezone.utc)

    class Animals:
        async def list_active_with_area(self):
            return [(first, None), (second, None)]

    class Reports:
        async def daily_stats_by_animal(self, *, start, end):
            assert start == datetime(2026, 9, 1, 16, 0, tzinfo=timezone.utc)
            assert end == datetime(2026, 9, 2, 16, 0, tzinfo=timezone.utc)
            return {second.id: (2, latest)}

    class Authorization:
        async def authorize(self, **kwargs):
            assert kwargs["organization_id"] == organization_id
            return SimpleNamespace()

    result = await TodayAnimalListService(Animals(), Reports(), Authorization()).list_today(
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        timezone_name="Asia/Taipei",
        now=datetime(2026, 9, 2, 0, 0, tzinfo=timezone.utc),
    )
    assert [item.candidate.animal.id for item in result.unreported] == [first.id]
    assert [item.candidate.animal.id for item in result.reported] == [second.id]
    assert result.reported[0].report_count == 2
    assert result.reported[0].latest_submitted_at == latest
    assert result.reported[0].candidate.animal.status == "active"


@pytest.mark.asyncio
async def test_today_list_has_independent_group_pagination_metadata() -> None:
    organization_id = uuid4()
    animals = [
        SimpleNamespace(id=uuid4(), organization_id=organization_id, status="active")
        for _ in range(5)
    ]

    class Animals:
        async def list_active_with_area(self):
            return [(animal, None) for animal in animals]

    class Reports:
        async def daily_stats_by_animal(self, **_kwargs):
            now = datetime.now(timezone.utc)
            return {animal.id: (1, now) for animal in animals[3:]}

    class Authorization:
        async def authorize(self, **_kwargs):
            return SimpleNamespace()

    result = await TodayAnimalListService(Animals(), Reports(), Authorization()).list_today(
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        timezone_name="UTC",
        page=1,
        page_size=1,
    )
    assert result.unreported_total == 3 and result.unreported_has_more
    assert result.reported_total == 2 and result.reported_has_more
