from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.animal_timeline import _serialize_day
from services.api.app.api.errors import DomainError
from services.api.app.application.media_access import MediaAccessService
from services.api.app.application.timeline_service import TimelineService
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake
from services.api.app.infrastructure.storage.ports import ObjectScope


class _ScopedTimelineRepository:
    def __init__(self, organization_id, reports, media_by_report):
        self.organization_id = organization_id
        self.reports_data = reports
        self.media_by_report = media_by_report

    async def reports(self, *, animal_id, start_date, end_date):
        return [
            report
            for report in self.reports_data
            if report.organization_id == self.organization_id
            and report.animal_id == animal_id
            and start_date <= report.submitted_at.date() <= end_date
        ]

    async def media_for_reports(self, report_ids):
        return {
            report_id: media
            for report_id, media in self.media_by_report.items()
            if report_id in report_ids
            and all(item.organization_id == self.organization_id for item in media)
        }


@pytest.mark.asyncio
async def test_staff_cannot_read_other_tenant_timeline_note_media_or_signed_url() -> None:
    organization_a = uuid4()
    organization_b = uuid4()
    animal_a = uuid4()
    animal_b = uuid4()
    report_a = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_a,
        animal_id=animal_a,
        submitted_at=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
        volunteer_user_id=uuid4(),
        animal_name_snapshot="A 動物",
        shelter_number_snapshot="A-01",
        note="A 私密心得",
        answers={"emotion": "emotion.calm"},
        answer_snapshots={"emotion": {"display_name": "平靜"}},
        status="saved",
        ai_job_status="pending",
    )
    report_b = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_b,
        animal_id=animal_b,
        submitted_at=datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc),
        volunteer_user_id=uuid4(),
        animal_name_snapshot="B 動物",
        shelter_number_snapshot="B-01",
        note="B 不應洩漏的心得",
        answers={"emotion": "emotion.alert"},
        answer_snapshots={"emotion": {"display_name": "緊張"}},
        status="saved",
        ai_job_status="pending",
    )
    media_b = SimpleNamespace(id=uuid4(), organization_id=organization_b)
    repository = _ScopedTimelineRepository(
        organization_a,
        [report_a, report_b],
        {report_b.id: [media_b]},
    )

    own_days = await TimelineService(repository).recent(
        animal_id=animal_a, end_date=date(2026, 8, 8)
    )
    own_payload = _serialize_day(
        own_days[-1], media_by_report=await repository.media_for_reports([report_a.id])
    )
    assert own_payload["reports"][0]["note"] == "A 私密心得"
    assert "B 不應洩漏的心得" not in str(own_payload)

    other_days = await TimelineService(repository).recent(
        animal_id=animal_b, end_date=date(2026, 8, 8)
    )
    assert other_days[-1].reports == []

    storage = InMemoryStorageFake()
    await storage.put(
        scope=ObjectScope(organization_b),
        key="reports/b/photo.jpg",
        data=b"clean",
        metadata=storage.metadata_for(b"clean", content_type="image/jpeg", checksum="b" * 64),
    )
    with pytest.raises(DomainError, match="照片不存在"):
        await MediaAccessService(storage, organization_a).signed_url(
            media_organization_id=organization_b,
            object_key="reports/b/photo.jpg",
        )
