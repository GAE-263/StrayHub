from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.ai_job_dispatch import create_ai_job
from services.api.app.application.async_job_types import (
    CELERY_JOB_TYPES,
    CELERY_TASK_BY_JOB_TYPE,
    LEGACY_POLLING_JOB_TYPES,
)
from services.worker import worker
from services.worker.app.tasks import care_report


class _Repository:
    def __init__(self):
        self.organization_id = uuid4()
        self.job = None

    async def create(self, job):
        self.job = job
        return job


def test_job_backend_ownership_is_mutually_exclusive() -> None:
    assert LEGACY_POLLING_JOB_TYPES.isdisjoint(CELERY_JOB_TYPES)
    assert LEGACY_POLLING_JOB_TYPES == frozenset()
    assert {"care_observation", "care_report_summary"} <= CELERY_JOB_TYPES
    assert set(CELERY_TASK_BY_JOB_TYPE) == CELERY_JOB_TYPES


@pytest.mark.asyncio
@pytest.mark.parametrize("job_type", ["care_observation", "care_report_summary"])
async def test_care_report_jobs_are_celery_owned(job_type: str) -> None:
    repository = _Repository()
    job = await create_ai_job(
        repository,
        target_type="care_report",
        target_id=uuid4(),
        job_type=job_type,
    )
    assert job.execution_backend == "celery"


@pytest.mark.asyncio
async def test_legacy_ai_iteration_is_fail_closed_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        worker,
        "get_worker_settings",
        lambda: SimpleNamespace(celery_ai_enabled=False),
    )

    class ForbiddenFactory:
        def __call__(self):
            raise AssertionError("disabled legacy AI iteration must not query or claim jobs")

    await worker.run_ai_iteration(
        ForbiddenFactory(),
        worker_id="test-worker",
        client=object(),
    )


def test_care_report_celery_task_is_fail_closed_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        care_report,
        "get_worker_settings",
        lambda: SimpleNamespace(celery_ai_enabled=False),
    )
    monkeypatch.setattr(
        care_report.runtime,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("disabled Celery task must not open runtime or claim a job")
        ),
    )

    assert (
        care_report.process_ai.run(
            job_id=str(uuid4()),
            resource_id=str(uuid4()),
            organization_id=str(uuid4()),
            expected_version=0,
        )
        == "disabled"
    )
