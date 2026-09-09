from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient
from services.api.app.config.settings import get_settings
from services.api.app.main import app
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.adoption_inquiry import AdoptionInquiry
from services.api.app.persistence.repositories.growth_diary_repository import (
    GrowthDiaryRepository,
    set_pending_draft,
)
from sqlalchemy import select

from tests.integration.test_growth_diary_webhook_flow import (
    _cleanup,
    _database_url,
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


async def _seed_second_animal(organization_id: UUID, animal_id: UUID) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute(
            """
            INSERT INTO animals
                (id, organization_id, name, shelter_number, status, is_adoptable,
                 size, energy, temperament, created_at, updated_at)
            VALUES ($1, $2, '旺旺', 'A201', 'active', true,
                    'medium', 'medium', '[]'::jsonb, now(), now())
            """,
            animal_id,
            organization_id,
        )
    finally:
        await connection.close()


def test_append_to_entry_merges_note_and_photo_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-growth-diary-repository")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    line_user_id = f"Urepo{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    try:
        client = TestClient(app)
        _submit_adoption_inquiry(client, line_user_id, organization_id, animal_id)
        asyncio.run(engine.dispose(close=False))

        async def scenario() -> None:
            async with session_factory() as session:
                async with session.begin():
                    await set_organization_scope(session, organization_id)
                    inquiry = await _fetch_inquiry(session, organization_id)
                    repo = GrowthDiaryRepository(session, organization_id)
                    entry = await repo.add_entry(
                        inquiry_id=inquiry.id,
                        animal_id=animal_id,
                        adopter_user_id=inquiry.adopter_user_id,
                        photo_key="growth-diary/day1/first.media",
                        photo_content_type="image/webp",
                        note="早上散步",
                    )

                    updated = await repo.append_to_entry(
                        entry.id,
                        inquiry_id=inquiry.id,
                        animal_id=animal_id,
                        adopter_user_id=inquiry.adopter_user_id,
                        photo_key="growth-diary/day1/second.media",
                        photo_content_type="image/webp",
                        note="晚上吃飯",
                    )

                    assert updated.id == entry.id
                    assert updated.note == "早上散步\n\n晚上吃飯"
                    assert updated.photo_keys == [
                        "growth-diary/day1/first.media",
                        "growth-diary/day1/second.media",
                    ]

                    # A text-only follow-up (no photo) must not touch photo_keys.
                    text_only = await repo.append_to_entry(
                        entry.id,
                        inquiry_id=inquiry.id,
                        animal_id=animal_id,
                        adopter_user_id=inquiry.adopter_user_id,
                        photo_key=None,
                        note="睡前再摸摸",
                    )
                    assert text_only.note == "早上散步\n\n晚上吃飯\n\n睡前再摸摸"
                    assert len(text_only.photo_keys) == 2

        asyncio.run(scenario())
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()


def test_set_pending_draft_resets_todays_thread_only_when_animal_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-picking the *same* animal (e.g. a repeat "新增一篇" tap) must leave
    an already-open thread alone so a same-day follow-up still merges onto
    it; switching to a *different* animal must clear it, since a stale
    current_entry_id would otherwise point at the wrong pet's entry."""
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-growth-diary-repository")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    other_animal_id = uuid4()
    line_user_id = f"Urepo{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    try:
        client = TestClient(app)
        _submit_adoption_inquiry(client, line_user_id, organization_id, animal_id)
        asyncio.run(_seed_second_animal(organization_id, other_animal_id))
        # A second full adoption flow for the second animal, same adopter —
        # the first draft is already "submitted" so a fresh one can start.
        _submit_adoption_inquiry(client, line_user_id, organization_id, other_animal_id)
        asyncio.run(engine.dispose(close=False))

        async def scenario() -> None:
            async with session_factory() as session:
                async with session.begin():
                    await set_organization_scope(session, organization_id)
                    inquiries = (
                        (
                            await session.execute(
                                select(AdoptionInquiry).where(
                                    AdoptionInquiry.organization_id == organization_id
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    inquiry = next(i for i in inquiries if i.target_animal_id == animal_id)
                    other_inquiry = next(
                        i for i in inquiries if i.target_animal_id == other_animal_id
                    )
                    repo = GrowthDiaryRepository(session, organization_id)
                    entry = await repo.add_entry(
                        inquiry_id=inquiry.id,
                        animal_id=animal_id,
                        adopter_user_id=inquiry.adopter_user_id,
                        photo_key=None,
                        note="今天的第一則",
                    )
                    draft = await set_pending_draft(
                        session,
                        adopter_user_id=inquiry.adopter_user_id,
                        organization_id=organization_id,
                        inquiry_id=inquiry.id,
                        animal_id=animal_id,
                    )
                    draft.current_entry_id = entry.id
                    date_today = draft.created_at.date()
                    draft.entry_date = date_today
                    await session.flush()

                    # Re-picking the same animal preserves the open thread.
                    same_animal = await set_pending_draft(
                        session,
                        adopter_user_id=inquiry.adopter_user_id,
                        organization_id=organization_id,
                        inquiry_id=inquiry.id,
                        animal_id=animal_id,
                    )
                    assert same_animal.current_entry_id == entry.id
                    assert same_animal.entry_date == date_today

                    # Switching to a different animal clears it.
                    switched = await set_pending_draft(
                        session,
                        adopter_user_id=inquiry.adopter_user_id,
                        organization_id=organization_id,
                        inquiry_id=other_inquiry.id,
                        animal_id=other_animal_id,
                    )
                    assert switched.current_entry_id is None
                    assert switched.entry_date is None

        asyncio.run(scenario())
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()
