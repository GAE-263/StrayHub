from datetime import datetime, timezone
from uuid import uuid4

import pytest
from services.api.app.application.report_correction import ReportCorrectionService
from services.api.app.domain.line_care_report_state import REQUIRED_ANSWER_KEYS
from services.api.app.persistence.models.care_report import CareReport


class _ReportRepository:
    def __init__(self, report: CareReport) -> None:
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


def _answers(suffix: str = "observed") -> dict[str, str]:
    return {
        key: (
            "care_completion.completed"
            if key == "care_completion"
            else "walk_completion.completed"
            if key == "walk_completion"
            else f"{key}.{suffix}"
        )
        for key in REQUIRED_ANSWER_KEYS
    }


def _report() -> CareReport:
    return CareReport(
        organization_id=uuid4(),
        animal_id=uuid4(),
        volunteer_user_id=uuid4(),
        membership_id=uuid4(),
        answers=_answers(),
        answer_snapshots={"emotion": {"code": "emotion.calm", "display_name": "平靜"}},
        animal_name_snapshot="原始動物",
        shelter_number_snapshot="A-01",
        note="原始心得",
        submitted_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_correction_preserves_original_history_then_archive_is_a_separate_audit() -> None:
    report = _report()
    target = type(
        "Animal",
        (),
        {"id": uuid4(), "status": "active", "name": "更正動物", "shelter_number": "A-02"},
    )()
    repository = _ReportRepository(report)
    audit = _Audit()
    service = ReportCorrectionService(repository, _AnimalRepository(target), audit=audit)

    corrected = await service.correct(
        report.id,
        actor_user_id=uuid4(),
        actor_role="STAFF",
        observations=_answers("corrected"),
        note="更正心得",
        animal_id=target.id,
        reason="原始回報選錯動物",
    )

    correction = repository.corrections[0]
    assert corrected.status == "amended"
    assert corrected.animal_id == target.id
    assert correction.before_data == {
        "answers": _answers(),
        "note": "原始心得",
        "animal_id": str(correction.original_animal_id),
    }
    assert correction.after_data["note"] == "更正心得"
    assert correction.after_data["animal_id"] == str(target.id)
    assert corrected.answer_snapshots["emotion"]["display_name"] == "平靜"
    assert [record["action"] for record in audit.records] == ["care_report.corrected"]

    archived = await service.archive(
        report.id, actor_user_id=uuid4(), reason="重複紀錄，保留原始與更正歷程"
    )

    assert archived.status == "archived"
    assert archived.archive_reason == "重複紀錄，保留原始與更正歷程"
    assert len(repository.corrections) == 1
    assert [record["action"] for record in audit.records] == [
        "care_report.corrected",
        "care_report.archived",
    ]
