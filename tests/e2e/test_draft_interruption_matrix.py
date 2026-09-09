from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.line_draft_service import LineDraftService


class _Repository:
    def __init__(self) -> None:
        self.organization_id = uuid4()
        self.items = []
        self.report_count = 0

    async def get_active_for_volunteer(self, volunteer_user_id):
        return next(
            (
                item
                for item in self.items
                if item.volunteer_user_id == volunteer_user_id and item.status == "active"
            ),
            None,
        )

    async def add(self, draft):
        if draft.id is None:
            draft.id = uuid4()
        self.items.append(draft)
        return draft

    async def get(self, draft_id):
        return next((item for item in self.items if item.id == draft_id), None)


INTERRUPTION_CASES = (
    ("close-answer-completion", "answering_completion"),
    ("close-answer-feeding", "answering_feeding"),
    ("close-answer-behavior", "answering_behavior"),
    ("switch-answer-completion", "answering_completion"),
    ("switch-answer-elimination", "answering_elimination"),
    ("switch-special-status", "answering_special_status"),
    ("network-answer", "answering_water"),
    ("network-photo-processing", "awaiting_media"),
    ("network-note", "awaiting_note"),
    ("lock-answer", "answering_activity"),
    ("lock-photo-processing", "awaiting_media"),
    ("lock-review", "reviewing"),
    ("back-answer", "answering_behavior"),
    ("back-photo-processing", "awaiting_media"),
    ("back-review", "reviewing"),
)


@pytest.mark.asyncio
@pytest.mark.parametrize("interruption, current_step", INTERRUPTION_CASES)
async def test_fifteen_interruptions_resume_saved_draft_without_creating_report(
    interruption: str, current_step: str
) -> None:
    repository = _Repository()
    service = LineDraftService(repository)
    volunteer_id = uuid4()
    animal_id = uuid4()
    draft, _ = await service.create(
        volunteer_user_id=volunteer_id,
        membership_id=uuid4(),
        animal_id=animal_id,
        source_event_id=interruption,
    )
    saved_at = draft.last_interaction_at
    draft.current_step = current_step
    draft.answers = {"care_completion": "care_completion.completed"}
    draft.note = "已保存心得"
    draft.photo_processing_status = "processed"

    resumed = await service.resume(draft.id, volunteer_user_id=volunteer_id)

    assert resumed.animal_id == animal_id
    assert resumed.answers == {"care_completion": "care_completion.completed"}
    assert resumed.note == "已保存心得"
    assert resumed.photo_processing_status == "processed"
    # Resume is itself an interaction and must refresh activity without changing
    # any saved answers, note, media state, or creating a report.
    assert resumed.last_interaction_at >= saved_at
    assert resumed.last_interaction_at.tzinfo == timezone.utc
    assert repository.report_count == 0


@pytest.mark.asyncio
async def test_cancelled_and_expired_drafts_cannot_become_reports() -> None:
    repository = _Repository()
    service = LineDraftService(repository)
    volunteer_id = uuid4()
    cancelled, _ = await service.create(
        volunteer_user_id=volunteer_id, membership_id=uuid4(), animal_id=uuid4()
    )
    await service.cancel(cancelled.id)
    assert cancelled.status == "cancelled"
    assert repository.report_count == 0

    expired, _ = await service.create(
        volunteer_user_id=volunteer_id, membership_id=uuid4(), animal_id=uuid4()
    )
    expired.expires_at = datetime.now(timezone.utc)
    with pytest.raises(DomainError, match="草稿已過期"):
        await service.resume(expired.id, volunteer_user_id=volunteer_id)
    assert expired.status == "expired"
    assert repository.report_count == 0
