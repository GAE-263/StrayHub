from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.report_submission import ReportSubmissionService
from services.api.app.domain.line_care_report_state import REQUIRED_ANSWER_KEYS
from services.api.app.persistence.models.animal import Animal


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None


class FakeDrafts:
    def __init__(self, draft) -> None:
        self.organization_id = draft.organization_id
        self.session = FakeSession()
        self.draft = draft

    async def get(self, draft_id):
        return self.draft if draft_id == self.draft.id else None

    async def media_ids(self, draft_id):
        return [self.draft_media_id]


class FakeReports:
    def __init__(self, organization_id):
        self.organization_id = organization_id
        self.items = []
        self.media: list[tuple[object, list[object]]] = []
        self.submitted_by_draft = None

    async def get_idempotent(self, *, volunteer_user_id, key):
        return None

    async def get_by_draft(self, draft_id):
        return self.submitted_by_draft

    async def add(self, report):
        self.items.append(report)
        return report

    async def add_idempotency(self, *, volunteer_user_id, key, report_id):
        return None

    async def attach_media(self, *, report_id, media_asset_ids):
        self.media.append((report_id, list(media_asset_ids)))


def make_draft(*, organization_id, volunteer_user_id, animal_id):
    return SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        volunteer_user_id=volunteer_user_id,
        membership_id=uuid4(),
        animal_id=animal_id,
        answers={
            **{key: f"{key}.observed" for key in REQUIRED_ANSWER_KEYS},
            "care_completion": "care_completion.completed",
            "walk_completion": "walk_completion.completed",
            "walk_reaction": "walk.willing",
        },
        note=None,
        status="active",
        current_step="reviewing",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        media_asset_ids=[uuid4()],
    )


@pytest.mark.asyncio
async def test_submit_promotes_draft_media_and_records_audit() -> None:
    organization_id = uuid4()
    volunteer_id = uuid4()
    animal_id = uuid4()
    draft = make_draft(
        organization_id=organization_id,
        volunteer_user_id=volunteer_id,
        animal_id=animal_id,
    )
    drafts = FakeDrafts(draft)
    drafts.draft_media_id = draft.media_asset_ids[0]
    reports = FakeReports(organization_id)
    audit_events: list[dict] = []

    class Audit:
        async def record(self, **kwargs):
            audit_events.append(kwargs)

    report = await ReportSubmissionService(
        drafts,
        reports,
        audit=Audit(),
    ).submit(
        draft_id=draft.id,
        volunteer_user_id=volunteer_id,
        animal=Animal(
            id=animal_id,
            organization_id=organization_id,
            name="小黑",
            shelter_number="A-001",
            status="active",
        ),
        idempotency_key="event-1",
        media_asset_ids=draft.media_asset_ids,
    )

    assert report.draft_id == draft.id
    assert reports.media == [(report.id, draft.media_asset_ids)]
    assert draft.status == "submitted"
    assert audit_events[0]["action"] == "care_report.submitted"


@pytest.mark.asyncio
async def test_submitting_the_same_draft_again_returns_the_existing_report() -> None:
    organization_id = uuid4()
    volunteer_id = uuid4()
    animal_id = uuid4()
    draft = make_draft(
        organization_id=organization_id,
        volunteer_user_id=volunteer_id,
        animal_id=animal_id,
    )
    draft.status = "submitted"
    drafts = FakeDrafts(draft)
    reports = FakeReports(organization_id)
    reports.submitted_by_draft = SimpleNamespace(id=uuid4(), draft_id=draft.id)

    result = await ReportSubmissionService(drafts, reports).submit(
        draft_id=draft.id,
        volunteer_user_id=volunteer_id,
        animal=Animal(
            id=animal_id,
            organization_id=organization_id,
            name="小黑",
            status="active",
        ),
        idempotency_key="a-new-event",
    )

    assert result is reports.submitted_by_draft
    assert reports.items == []
