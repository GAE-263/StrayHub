from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from services.api.app.application.adoption_inquiry_service import AdoptionInquiryInboxService
from services.api.app.config.settings import get_settings
from services.api.app.main import app
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.adoption_inquiry import AdoptionInquiry
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


def test_list_filters_by_search_path_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-adoption-inquiry-inbox")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    line_user_id = f"Uinquiry{uuid4().hex}"
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

                service = AdoptionInquiryInboxService(session, organization_id)

                all_items = await service.list()
                assert all_items["total"] == 1
                assert all_items["items"][0]["id"] == str(inquiry.id)
                assert all_items["items"][0]["status"] == "new"
                assert all_items["items"][0]["animal_name"] == "旺來"

                # 查看問卷: codes resolved to their Chinese label/option text,
                # in questionnaire order, not the raw dict.
                display = all_items["items"][0]["answers_display"]
                assert display[0] == {
                    "key": "housing_type",
                    "label": "居住環境",
                    "value": "🏢 小坪數公寓",
                }
                assert display[1] == {
                    "key": "dog_experience",
                    "label": "養狗經驗",
                    "value": "🌱 這是我第一次",
                }
                assert [row["key"] for row in display] == [
                    "housing_type",
                    "dog_experience",
                    "other_pets",
                    "household_members",
                    "work_schedule",
                    "parenting_style",
                    "patience_level",
                    "adoption_motivation",
                    "adopter_name",
                    "contact_time",
                    "phone_number",
                ]
                # Contact-info fields are free text, not coded options —
                # shown as-is rather than run through _answer_display.
                contact_row = next(row for row in display if row["key"] == "adopter_name")
                assert contact_row["value"] == "王小明"

                # Search matches animal name, shelter number (seeded A200),
                # adopter name, and phone number.
                assert (await service.list(search="旺來"))["total"] == 1
                assert (await service.list(search="A200"))["total"] == 1
                assert (await service.list(search="王小明"))["total"] == 1
                assert (await service.list(search="0911222333"))["total"] == 1
                assert (await service.list(search="不存在的關鍵字"))["total"] == 0

                # Path filter.
                assert (await service.list(path="specific_animal"))["total"] == 1
                assert (await service.list(path="recommend_me"))["total"] == 0

                # Status transition. status_updated_by_user_id is a real FK
                # to users, so the actor must be a real row — the adopter's
                # own user id (already seeded by _submit_adoption_inquiry)
                # stands in here; who the actor semantically represents
                # doesn't matter for exercising the persistence mechanics.
                updated = await service.set_status(
                    inquiry.id,
                    inquiry_status="contacted",
                    actor_user_id=inquiry.adopter_user_id,
                )
                assert updated["status"] == "contacted"
                assert updated["status_updated_at"] is not None
                assert (await service.list(inquiry_status="contacted"))["total"] == 1
                assert (await service.list(inquiry_status="new"))["total"] == 0

                # Pagination.
                page = await service.list(page=1, page_size=1)
                assert len(page["items"]) == 1
                assert page["total"] == 1

        asyncio.run(scenario())
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()


def test_set_status_rejects_unknown_value_and_missing_inquiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-adoption-inquiry-inbox")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    line_user_id = f"Uinquiry{uuid4().hex}"
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

                service = AdoptionInquiryInboxService(session, organization_id)
                with pytest.raises(Exception, match="不支援的狀態"):
                    await service.set_status(
                        inquiry.id, inquiry_status="approved", actor_user_id=uuid4()
                    )
                with pytest.raises(Exception, match="找不到"):
                    await service.set_status(
                        uuid4(), inquiry_status="contacted", actor_user_id=uuid4()
                    )

        asyncio.run(scenario())
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()
