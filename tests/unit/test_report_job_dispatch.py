from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application import report_job_dispatch as module
from services.api.app.application.report_job_dispatch import ReportJobDispatchService


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _Session:
    def __init__(self, report):
        self.report = report
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def begin(self):
        return _Transaction()

    async def execute(self, _statement, *_args, **_kwargs):
        return SimpleNamespace(scalar_one_or_none=lambda: self.report)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_report_job_dispatch_commits_after_report_exists(monkeypatch) -> None:
    organization_id = uuid4()
    report = SimpleNamespace(id=uuid4(), organization_id=organization_id, ai_job_status="saved")
    session = _Session(report)

    def factory():
        return session

    service = ReportJobDispatchService(factory)

    async def fake_create(repository, **kwargs):
        repository.session.add(SimpleNamespace(**kwargs))
        return repository.session.added[-1]

    monkeypatch.setattr(module, "create_ai_job", fake_create)

    assert await service.dispatch(organization_id=organization_id, report_id=report.id)
    assert report.ai_job_status == "enqueued"
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_enqueue_failure_preserves_report_and_marks_reconciliation_state(monkeypatch) -> None:
    organization_id = uuid4()
    report = SimpleNamespace(id=uuid4(), organization_id=organization_id, ai_job_status="saved")
    session = _Session(report)
    service = ReportJobDispatchService(lambda: session)

    async def fail_create(*_args, **_kwargs):
        raise RuntimeError("adapter unavailable")

    monkeypatch.setattr(module, "create_ai_job", fail_create)

    assert not await service.dispatch(organization_id=organization_id, report_id=report.id)
    assert report.ai_job_status == "enqueue_failed"
