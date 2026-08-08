from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.report_submission import ReportSubmissionService
from services.api.app.domain.line_care_report_state import REQUIRED_ANSWER_KEYS
from services.api.app.persistence.models.animal import Animal


def _complete_answers() -> dict[str, str]:
    values = {key: f"{key}.observed" for key in REQUIRED_ANSWER_KEYS}
    values.update(
        care_completion="care_completion.completed",
        walk_completion="walk_completion.completed",
        walk_reaction="walk.willing",
    )
    return values


def _draft(organization_id, volunteer_id, animal_id, answers):
    return SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        volunteer_user_id=volunteer_id,
        membership_id=uuid4(),
        animal_id=animal_id,
        answers=answers,
        note=None,
        status="active",
        current_step="reviewing",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )


class Drafts:
    def __init__(self, draft):
        self.organization_id = draft.organization_id
        self.draft = draft
        self.session = SimpleNamespace(flush=lambda: None)

    async def get(self, draft_id):
        return self.draft if draft_id == self.draft.id else None

    async def media_ids(self, _draft_id):
        return []


class Reports:
    def __init__(self, organization_id):
        self.organization_id = organization_id

    async def get_idempotent(self, **_kwargs):
        return None

    async def get_by_draft(self, _draft_id):
        return None

    async def add(self, report):
        return report

    async def add_idempotency(self, **_kwargs):
        return None

    async def attach_media(self, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_submission_rejects_missing_answer_before_creating_report() -> None:
    organization_id = uuid4()
    volunteer_id = uuid4()
    animal_id = uuid4()
    draft = _draft(organization_id, volunteer_id, animal_id, _complete_answers())
    draft.answers.pop("emotion")
    with pytest.raises(DomainError, match="缺少必要"):
        await ReportSubmissionService(Drafts(draft), Reports(organization_id)).submit(
            draft_id=draft.id,
            volunteer_user_id=volunteer_id,
            animal=Animal(
                id=animal_id,
                organization_id=organization_id,
                name="小黑",
                status="active",
            ),
            idempotency_key="event-1",
        )


@pytest.mark.asyncio
async def test_submission_rejects_walk_completion_as_walk_reaction() -> None:
    organization_id = uuid4()
    volunteer_id = uuid4()
    animal_id = uuid4()
    answers = _complete_answers()
    answers["walk_reaction"] = "walk_completion.completed"
    draft = _draft(organization_id, volunteer_id, animal_id, answers)
    with pytest.raises(DomainError, match="不可混用"):
        await ReportSubmissionService(Drafts(draft), Reports(organization_id)).submit(
            draft_id=draft.id,
            volunteer_user_id=volunteer_id,
            animal=Animal(
                id=animal_id,
                organization_id=organization_id,
                name="小黑",
                status="active",
            ),
            idempotency_key="event-2",
        )
