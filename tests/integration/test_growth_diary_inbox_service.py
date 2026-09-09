from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from services.api.app.application.growth_diary_service import GrowthDiaryInboxService
from services.api.app.config.settings import get_settings
from services.api.app.main import app
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.adoption_inquiry import AdoptionInquiry
from services.api.app.persistence.repositories.growth_diary_repository import (
    GrowthDiaryRepository,
)
from sqlalchemy import select

from tests.integration.test_growth_diary_webhook_flow import (
    _cleanup,
    _seed,
    _submit_adoption_inquiry,
)


async def _fetch_inquiry(session, organization_id) -> AdoptionInquiry:
    return (
        (
            await session.execute(
                select(AdoptionInquiry).where(AdoptionInquiry.organization_id == organization_id)
            )
        )
        .scalars()
        .one()
    )


def test_list_filters_by_status_mood_and_search_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-growth-diary-inbox")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    line_user_id = f"Uinbox{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    try:
        client = TestClient(app)
        _submit_adoption_inquiry(client, line_user_id, organization_id, animal_id)
        # Matches _post()'s own defensive dispose (test_growth_diary_webhook_
        # flow.py) — the "submit" action's AI-suitability background task
        # can still be tearing down its own event-loop-bound connections
        # when the very next asyncio.run() starts a fresh loop otherwise.
        asyncio.run(engine.dispose(close=False))

        async def scenario() -> None:
            async with session_factory() as session:
                async with session.begin():
                    await set_organization_scope(session, organization_id)
                    inquiry = await _fetch_inquiry(session, organization_id)
                    repo = GrowthDiaryRepository(session, organization_id)
                    new_entry = await repo.add_entry(
                        inquiry_id=inquiry.id,
                        animal_id=animal_id,
                        adopter_user_id=inquiry.adopter_user_id,
                        photo_key=None,
                        note="今天精神很好",
                    )
                    new_entry.ai_mood = "positive"
                    concern_entry = await repo.add_entry(
                        inquiry_id=inquiry.id,
                        animal_id=animal_id,
                        adopter_user_id=inquiry.adopter_user_id,
                        photo_key=None,
                        note="今天吃得比較少，有點沒精神",
                    )
                    concern_entry.ai_mood = "concern"

                service = GrowthDiaryInboxService(session, organization_id)

                # Default list sees both entries, newest first.
                all_items = await service.list()
                assert all_items["total"] == 2
                assert [item["id"] for item in all_items["items"]] == [
                    str(concern_entry.id),
                    str(new_entry.id),
                ]
                # Newly created entries default to "new".
                assert all(item["status"] == "new" for item in all_items["items"])

                # Filter by mood.
                concern_only = await service.list(mood="concern")
                assert [item["id"] for item in concern_only["items"]] == [str(concern_entry.id)]

                # Search matches the shelter number seeded by _seed (A200).
                by_shelter_number = await service.list(search="A200")
                assert by_shelter_number["total"] == 2

                # Search also matches note text.
                by_note = await service.list(search="沒精神")
                assert [item["id"] for item in by_note["items"]] == [str(concern_entry.id)]

                # set_status transitions and is reflected in a status filter.
                updated = await service.set_status(
                    concern_entry.id,
                    entry_status="reviewed",
                    actor_user_id=inquiry.adopter_user_id,
                )
                assert updated["status"] == "reviewed"
                reviewed_only = await service.list(entry_status="reviewed")
                assert [item["id"] for item in reviewed_only["items"]] == [str(concern_entry.id)]
                still_new = await service.list(entry_status="new")
                assert [item["id"] for item in still_new["items"]] == [str(new_entry.id)]

                # Pagination.
                page_one = await service.list(page=1, page_size=1)
                assert len(page_one["items"]) == 1
                assert page_one["total"] == 2

        asyncio.run(scenario())
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()


def test_set_status_rejects_unknown_value_and_missing_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-growth-diary-inbox")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    line_user_id = f"Uinbox{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    try:
        client = TestClient(app)
        _submit_adoption_inquiry(client, line_user_id, organization_id, animal_id)
        # Matches _post()'s own defensive dispose (test_growth_diary_webhook_
        # flow.py) — the "submit" action's AI-suitability background task
        # can still be tearing down its own event-loop-bound connections
        # when the very next asyncio.run() starts a fresh loop otherwise.
        asyncio.run(engine.dispose(close=False))

        async def scenario() -> None:
            async with session_factory() as session:
                async with session.begin():
                    await set_organization_scope(session, organization_id)
                    inquiry = await _fetch_inquiry(session, organization_id)
                    entry = await GrowthDiaryRepository(session, organization_id).add_entry(
                        inquiry_id=inquiry.id,
                        animal_id=animal_id,
                        adopter_user_id=inquiry.adopter_user_id,
                        photo_key=None,
                        note="測試",
                    )

                service = GrowthDiaryInboxService(session, organization_id)
                with pytest.raises(Exception, match="不支援的狀態"):
                    await service.set_status(
                        entry.id,
                        entry_status="archived",
                        actor_user_id=inquiry.adopter_user_id,
                    )
                with pytest.raises(Exception, match="不存在|找不到"):
                    await service.set_status(
                        uuid4(),
                        entry_status="reviewed",
                        actor_user_id=inquiry.adopter_user_id,
                    )

        asyncio.run(scenario())
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()
