from uuid import uuid4

import pytest
from services.api.app.application.ai_job_dispatch import create_ai_job, reconcile_ai_jobs
from services.api.app.persistence.models.ai_job import AIProcessingJob


class FakeJobRepository:
    def __init__(self) -> None:
        self.organization_id = uuid4()
        self.jobs: list[AIProcessingJob] = []

    async def create(self, job: AIProcessingJob) -> AIProcessingJob:
        self.jobs.append(job)
        return job

    async def pending_reconciliation(self) -> list[AIProcessingJob]:
        return [job for job in self.jobs if job.status in {"pending_enqueue", "enqueue_failed"}]


@pytest.mark.asyncio
async def test_ai_job_foundation_has_version_trace_and_org_scoped_target() -> None:
    repository = FakeJobRepository()
    target = uuid4()
    job = await create_ai_job(repository, target_type="care_report", target_id=target)

    assert job.organization_id == repository.organization_id
    assert job.target_id == target
    assert all(
        getattr(job, field)
        for field in (
            "provider",
            "model_name",
            "model_version",
            "prompt_template_id",
            "prompt_version",
            "output_schema_version",
        )
    )
    assert job.status == "pending_enqueue"


@pytest.mark.asyncio
async def test_ai_job_reconciliation_is_idempotent_and_keeps_scope() -> None:
    repository = FakeJobRepository()
    job = await create_ai_job(repository, target_type="care_report", target_id=uuid4())
    job.status = "enqueue_failed"

    first = await reconcile_ai_jobs(repository)
    second = await reconcile_ai_jobs(repository)

    assert first == second == [job]
    assert job.status == "pending_enqueue"
    assert job.organization_id == repository.organization_id
