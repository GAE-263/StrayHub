from pathlib import Path

import pytest
from services.api.app.main import app


@pytest.mark.e2e
def test_report_workflow_covers_inbox_detail_and_traceable_mutations() -> None:
    inbox = Path("apps/web/app/(management)/reports/page.tsx").read_text()
    detail = Path("apps/web/app/(management)/reports/[reportId]/page.tsx").read_text()
    api = Path("services/api/app/api/report_inbox.py").read_text()

    assert "回報收件匣" in inbox
    assert "Report Inbox" not in inbox
    assert "answers" in detail
    assert "media_ids" in detail
    assert "ai_observations" in detail
    assert "correction" in detail
    assert "archive" in detail
    assert "reason" in api
    assert "/v1/management/reports/{report_id}" in app.openapi()["paths"]


@pytest.mark.e2e
def test_report_workflow_keeps_original_data_when_ai_or_media_is_unavailable() -> None:
    service = Path("services/api/app/application/report_inbox_service.py").read_text()
    correction = Path("services/api/app/application/report_correction.py").read_text()

    assert '"answers": report.answers' in service
    assert '"media_ids": media_ids or []' in service
    assert "archived_at" in correction
    assert "before" in correction or "before_data" in correction
