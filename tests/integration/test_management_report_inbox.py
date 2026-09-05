from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.report_inbox_service import ReportInboxService


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Session:
    async def scalar(self, _query):
        return 1

    async def execute(self, _query):
        if "volunteer_profiles" in str(_query):
            return _Result([])
        report = SimpleNamespace(
            id=uuid4(),
            organization_id=uuid4(),
            animal_id=uuid4(),
            animal_name_snapshot="小森",
            shelter_number_snapshot="A-001",
            volunteer_user_id=uuid4(),
            membership_id=uuid4(),
            answers={"feeding": "feeding.normal"},
            answer_snapshots={"feeding": {"code": "feeding.normal"}},
            note="原始心得",
            status="saved",
            ai_job_status="succeeded",
            submitted_at=datetime.now(timezone.utc),
            archived_at=None,
        )
        animal = SimpleNamespace(name="小森")
        return _Result([(report, animal)])


@pytest.mark.asyncio
async def test_report_inbox_keeps_original_answers_and_scope_summary() -> None:
    result = await ReportInboxService(_Session(), uuid4()).list(
        from_date=None,
        to_date=None,
        animal_id=None,
        report_status="saved",
        page=1,
        page_size=20,
    )

    assert result["items"][0]["answers"] == {"feeding": "feeding.normal"}
    assert result["items"][0]["note"] == "原始心得"
