from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.report_submission import ReportSubmissionService
from services.api.app.persistence.models.animal import Animal


def _answers():
    return {
        "walk_completion": "walk_completion.completed",
        "activity": "activity.usual",
        "gait": "gait.normal",
        "defecation": "defecation.normal",
        "animal_interaction": "animal_interaction.friendly",
        "appearance_special_status": "appearance.none_found",
    }


@pytest.mark.asyncio
async def test_same_day_reports_from_multiple_volunteers_keep_original_values() -> None:
    organization_id = uuid4()
    animal_id = uuid4()
    reports = []

    class Drafts:
        def __init__(self):
            self.organization_id = organization_id
            self.session = SimpleNamespace(flush=self.flush)
            self.items = []

        async def flush(self):
            return None

        async def get(self, draft_id):
            return next((item for item in self.items if item.id == draft_id), None)

        async def media_ids(self, _draft_id):
            return []

    class ReportRepo:
        def __init__(self):
            self.organization_id = organization_id

        async def get_idempotent(self, **_kwargs):
            return None

        async def get_by_draft(self, _draft_id):
            return None

        async def add(self, report):
            reports.append(report)
            return report

        async def add_idempotency(self, **_kwargs):
            return None

        async def attach_media(self, **_kwargs):
            return None

    drafts = Drafts()
    animal = Animal(id=animal_id, organization_id=organization_id, name="小黑", status="active")
    volunteer_id = uuid4()
    for value, story in (("activity.usual", "第一次"), ("activity.higher", "第二次")):
        draft = SimpleNamespace(
            id=uuid4(),
            organization_id=organization_id,
            volunteer_user_id=volunteer_id,
            membership_id=uuid4(),
            animal_id=animal_id,
            answers={**_answers(), "activity": value},
            note=None,
            story=story,
            status="active",
            current_step="reviewing",
            expires_at=datetime.now(timezone.utc),
        )
        drafts.items.append(draft)
        await ReportSubmissionService(drafts, ReportRepo()).submit(
            draft_id=draft.id,
            volunteer_user_id=volunteer_id,
            animal=animal,
            idempotency_key=str(uuid4()),
        )

    assert len(reports) == 2
    assert {report.answers["activity"] for report in reports} == {
        "activity.usual",
        "activity.higher",
    }
    assert {report.story for report in reports} == {"第一次", "第二次"}
