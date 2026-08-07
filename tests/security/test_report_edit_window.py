from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.report_correction import ReportCorrectionService


@pytest.mark.asyncio
async def test_volunteer_cannot_edit_after_24_hours_or_hard_delete() -> None:
    report = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        volunteer_user_id=uuid4(),
        submitted_at=datetime.now(timezone.utc) - timedelta(days=2),
        answers={},
        note=None,
        animal_id=uuid4(),
        status="saved",
        archived_at=None,
    )

    class Reports:
        async def get(self, _report_id):
            return report

        async def add_correction(self, _correction):
            return None

    with pytest.raises(DomainError, match="不能修改"):
        await ReportCorrectionService(Reports(), SimpleNamespace()).correct(
            report.id,
            actor_user_id=report.volunteer_user_id,
            actor_role="VOLUNTEER",
            observations=None,
            note="late",
            animal_id=None,
            reason="late correction",
        )
    assert not hasattr(Reports, "delete")
