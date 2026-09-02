from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.report_correction import ReportCorrectionService
from services.api.app.domain.line_care_report_state import REQUIRED_ANSWER_KEYS
from services.api.app.persistence.models.care_report import CareReport


class _ReportRepository:
    def __init__(self, report: CareReport) -> None:
        self.organization_id = report.organization_id
        self.report = report
        self.corrections = []

    async def get(self, report_id):
        return self.report if report_id == self.report.id else None

    async def add_correction(self, correction):
        self.corrections.append(correction)
        return correction


class _AnimalRepository:
    def __init__(self, animal) -> None:
        self.animal = animal

    async def get(self, animal_id):
        return self.animal if animal_id == self.animal.id else None


class _Audit:
    def __init__(self) -> None:
        self.records = []

    async def record(self, **values):
        self.records.append(values)


def _report():
    now = datetime.now(timezone.utc)
    answers = {
        key: ("walk_completion.completed" if key == "walk_completion" else f"{key}.observed")
        for key in REQUIRED_ANSWER_KEYS
    }
    return CareReport(
        organization_id=uuid4(),
        animal_id=uuid4(),
        volunteer_user_id=uuid4(),
        membership_id=uuid4(),
        answers=answers,
        animal_name_snapshot="小黑",
        shelter_number_snapshot="A-01",
        submitted_at=now,
    )


@pytest.mark.asyncio
async def test_owner_can_correct_within_edit_window_and_history_is_saved() -> None:
    report = _report()
    target = type(
        "Animal", (), {"id": uuid4(), "status": "active", "name": "小白", "shelter_number": "A-02"}
    )()
    repository = _ReportRepository(report)
    audit = _Audit()
    service = ReportCorrectionService(repository, _AnimalRepository(target), audit=audit)

    corrected = await service.correct(
        report.id,
        actor_user_id=report.volunteer_user_id,
        actor_role="VOLUNTEER",
        observations={
            **{key: f"{key}.corrected" for key in REQUIRED_ANSWER_KEYS if key != "walk_completion"},
            "walk_completion": "walk_completion.partially_completed",
        },
        note="補充觀察",
        animal_id=target.id,
        reason="送出時選錯動物",
    )

    assert corrected.status == "amended"
    assert corrected.animal_id == target.id
    assert len(repository.corrections) == 1
    assert repository.corrections[0].original_animal_id != target.id
    assert audit.records[0]["action"] == "care_report.corrected"
    assert audit.records[0]["before"]["animal_id"] != audit.records[0]["after"]["animal_id"]


@pytest.mark.asyncio
async def test_owner_cannot_correct_after_edit_window() -> None:
    report = _report()
    report.submitted_at = datetime.now(timezone.utc) - timedelta(days=2)
    repository = _ReportRepository(report)

    with pytest.raises(DomainError, match="不能修改"):
        await ReportCorrectionService(
            repository, _AnimalRepository(type("Animal", (), {})())
        ).correct(
            report.id,
            actor_user_id=report.volunteer_user_id,
            actor_role="VOLUNTEER",
            observations=None,
            note="補充",
            animal_id=None,
            reason="修正",
        )


@pytest.mark.asyncio
async def test_staff_can_archive_without_deleting_report() -> None:
    report = _report()
    repository = _ReportRepository(report)
    audit = _Audit()
    service = ReportCorrectionService(
        repository, _AnimalRepository(type("Animal", (), {})()), audit=audit
    )

    archived = await service.archive(
        report.id,
        actor_user_id=uuid4(),
        reason="重複紀錄",
    )

    assert archived.status == "archived"
    assert archived.archived_by is not None
    assert audit.records[0]["action"] == "care_report.archived"
