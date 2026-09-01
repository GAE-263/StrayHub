from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.report_submission import ReportSubmissionService
from services.api.app.persistence.models.animal import Animal


def _answers() -> dict[str, str]:
    return {
        "walk_completion": "walk_completion.completed",
        "activity": "activity.usual",
        "gait": "gait.normal",
        "defecation": "defecation.normal",
        "animal_interaction": "animal_interaction.friendly",
        "appearance_special_status": "appearance.none_found",
    }


@pytest.mark.asyncio
async def test_duplicate_submit_with_same_idempotency_key_returns_one_report() -> None:
    organization_id = uuid4()
    volunteer_id = uuid4()
    animal_id = uuid4()
    draft = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        volunteer_user_id=volunteer_id,
        membership_id=uuid4(),
        animal_id=animal_id,
        answers=_answers(),
        note=None,
        status="active",
        current_step="reviewing",
    )

    class Drafts:
        def __init__(self):
            self.organization_id = organization_id
            self.session = SimpleNamespace(flush=self.flush)

        async def flush(self):
            return None

        async def get(self, draft_id):
            return draft if draft_id == draft.id else None

        async def media_ids(self, _draft_id):
            return []

    class Reports:
        def __init__(self):
            self.organization_id = organization_id
            self.report = None

        async def get_idempotent(self, *, volunteer_user_id, key):
            return self.report if key == "same-event" else None

        async def get_by_draft(self, _draft_id):
            return self.report

        async def add(self, report):
            self.report = report
            return report

        async def add_idempotency(self, **_kwargs):
            return None

        async def attach_media(self, **_kwargs):
            return None

    drafts = Drafts()
    reports = Reports()
    animal = Animal(id=animal_id, organization_id=organization_id, name="小黑", status="active")
    service = ReportSubmissionService(drafts, reports)
    first = await service.submit(
        draft_id=draft.id,
        volunteer_user_id=volunteer_id,
        animal=animal,
        idempotency_key="first-event",
    )
    reports.report = first
    second = await service.submit(
        draft_id=draft.id,
        volunteer_user_id=volunteer_id,
        animal=animal,
        idempotency_key="same-event",
    )
    assert second is first
