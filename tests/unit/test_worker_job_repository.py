from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.worker.app.persistence import job_repository as module
from services.worker.app.persistence.job_repository import WorkerJobRepository


class _Result:
    def __init__(self, value=None, values=None):
        self.value = value
        self.values = values or []

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return iter(self.values)


class _Session:
    def __init__(self, *results):
        self.results = list(results)
        self.flushed = 0

    async def execute(self, _statement, _parameters=None):
        return self.results.pop(0)

    async def flush(self):
        self.flushed += 1


@pytest.mark.asyncio
async def test_claim_sets_worker_owned_lock(monkeypatch) -> None:
    monkeypatch.setattr(module, "set_organization_scope", _noop_scope)
    organization_id = uuid4()
    job = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        status="pending_enqueue",
        available_at=None,
        claim_token=None,
        claimed_at=None,
        claimed_by=None,
        started_at=None,
        created_at=datetime.now(timezone.utc),
    )
    session = _Session(_Result(job))

    claimed = await WorkerJobRepository(session, organization_id, worker_id="worker-a").claim_next()

    assert claimed is not None
    _, token = claimed
    assert job.status == "running"
    assert job.claimed_by == "worker-a"
    assert job.claim_token == token
    assert len(token) >= 32


@pytest.mark.asyncio
async def test_finish_rejects_a_claim_owned_by_another_worker(monkeypatch) -> None:
    monkeypatch.setattr(module, "set_organization_scope", _noop_scope)
    organization_id = uuid4()
    job = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        status="running",
        claim_token="token-a",
        claimed_by="worker-a",
    )
    session = _Session(_Result(job))

    with pytest.raises(DomainError, match="Claim"):
        await WorkerJobRepository(session, organization_id, worker_id="worker-b").finish(
            job.id, claim_token="token-a", status="succeeded"
        )


@pytest.mark.asyncio
async def test_reclaim_stale_job_returns_it_to_retry_queue(monkeypatch) -> None:
    monkeypatch.setattr(module, "set_organization_scope", _noop_scope)
    organization_id = uuid4()
    job = SimpleNamespace(
        organization_id=organization_id,
        status="running",
        claimed_at=datetime.now(timezone.utc) - timedelta(hours=1),
        retry_count=0,
        available_at=None,
        claim_token="token-a",
        claimed_by="worker-a",
    )
    session = _Session(_Result(values=[job]))

    count = await WorkerJobRepository(session, organization_id, worker_id="worker-b").reclaim_stale(
        timeout_seconds=60
    )

    assert count == 1
    assert job.status == "retry_wait"
    assert job.retry_count == 1
    assert job.claim_token is None


@pytest.mark.asyncio
async def test_reclaim_stale_job_stops_at_retry_limit(monkeypatch) -> None:
    monkeypatch.setattr(module, "set_organization_scope", _noop_scope)
    organization_id = uuid4()
    job = SimpleNamespace(
        organization_id=organization_id,
        status="running",
        claimed_at=datetime.now(timezone.utc) - timedelta(hours=1),
        retry_count=2,
        available_at=None,
        completed_at=None,
        failure_reason=None,
        claim_token="token-a",
        claimed_by="worker-a",
    )
    session = _Session(_Result(values=[job]))

    await WorkerJobRepository(session, organization_id, worker_id="worker-b").reclaim_stale(
        timeout_seconds=60,
        max_retries=3,
    )

    assert job.status == "failed"
    assert job.retry_count == 3
    assert job.failure_reason == "stale_claim_exhausted"
    assert job.completed_at is not None


async def _noop_scope(_session, _organization_id):
    return None
