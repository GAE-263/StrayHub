from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.report_job_dispatch import ReportJobDispatchService


@pytest.mark.asyncio
async def test_reconciliation_retries_enqueue_failed_report_without_new_report(monkeypatch) -> None:
    organization_id = uuid4()
    report = SimpleNamespace(
        id=uuid4(), organization_id=organization_id, ai_job_status="enqueue_failed"
    )
    calls = []

    class Session:
        def __init__(self):
            self.report = report

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def begin(self):
            return self

        async def execute(self, _statement):
            return SimpleNamespace(scalar_one_or_none=lambda: self.report)

    async def fake_create(*_args, **_kwargs):
        calls.append(True)

    monkeypatch.setattr(
        "services.api.app.application.report_job_dispatch.create_ai_job", fake_create
    )
    service = ReportJobDispatchService(lambda: Session())
    assert await service.reconcile(organization_id=organization_id, report_id=report.id)
    assert report.ai_job_status == "enqueued"
    assert len(calls) == 1
