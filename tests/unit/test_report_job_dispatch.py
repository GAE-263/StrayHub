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
    def __init__(self, report, *, existing_job_ids=None):
        self.report = report
        self.added = []
        self.existing_job_ids = existing_job_ids or []
        self.execute_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def begin(self):
        return _Transaction()

    async def execute(self, _statement, *_args, **_kwargs):
        self.execute_count += 1
        return SimpleNamespace(
            scalar_one_or_none=lambda: self.report,
            scalars=lambda: self.existing_job_ids if self.execute_count > 1 else [],
        )

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_report_job_dispatch_commits_after_report_exists(monkeypatch) -> None:
    organization_id = uuid4()
    report = SimpleNamespace(id=uuid4(), organization_id=organization_id, ai_job_status="saved")
    summary_job_id = uuid4()
    session = _Session(report, existing_job_ids=[summary_job_id])
    dispatched = []

    def factory():
        return session

    service = ReportJobDispatchService(factory, ai_enabled=True)

    async def fake_create(repository, **kwargs):
        repository.session.add(SimpleNamespace(id=uuid4(), **kwargs))
        return repository.session.added[-1]

    monkeypatch.setattr(module, "create_ai_job", fake_create)

    async def fake_dispatch(job_id, dispatched_organization_id):
        dispatched.append((job_id, dispatched_organization_id))
        return True

    monkeypatch.setattr(module, "dispatch_ai_job", fake_dispatch)

    assert await service.dispatch(organization_id=organization_id, report_id=report.id)
    assert report.ai_job_status == "enqueued"
    assert len(session.added) == 1
    assert {job_id for job_id, _organization_id in dispatched} == {
        summary_job_id,
        session.added[0].id,
    }
    assert {org_id for _job_id, org_id in dispatched} == {organization_id}


@pytest.mark.asyncio
async def test_enqueue_failure_preserves_report_and_marks_reconciliation_state(monkeypatch) -> None:
    organization_id = uuid4()
    report = SimpleNamespace(id=uuid4(), organization_id=organization_id, ai_job_status="saved")
    session = _Session(report)
    service = ReportJobDispatchService(lambda: session, ai_enabled=True)

    async def fail_create(*_args, **_kwargs):
        raise RuntimeError("adapter unavailable")

    monkeypatch.setattr(module, "create_ai_job", fail_create)

    assert not await service.dispatch(organization_id=organization_id, report_id=report.id)
    assert report.ai_job_status == "enqueue_failed"


@pytest.mark.asyncio
async def test_disabled_mode_does_not_open_session_or_create_jobs() -> None:
    opened = False

    def factory():
        nonlocal opened
        opened = True
        raise AssertionError("disabled dispatch must not open a database session")

    service = ReportJobDispatchService(factory, ai_enabled=False)
    assert await service.dispatch(organization_id=uuid4(), report_id=uuid4())
    assert opened is False
