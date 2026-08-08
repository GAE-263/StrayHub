from uuid import uuid4

import pytest
from services.api.app.application.ai_job_dispatch import create_ai_job
from services.worker.app.handlers.ai_handler import AIJobHandler
from services.worker.app.infrastructure.mock_ai_adapter import MockAIAdapter


class FakeJobRepository:
    def __init__(self):
        self.organization_id = uuid4()
        self.value = None

    async def create(self, value):
        self.value = value
        return value


@pytest.mark.asyncio
async def test_ai_job_keeps_non_empty_version_trace() -> None:
    repository = FakeJobRepository()
    job = await create_ai_job(repository, target_type="care_report", target_id=uuid4())

    assert job.organization_id == repository.organization_id
    assert job.provider
    assert job.model_name
    assert job.model_version
    assert job.prompt_template_id
    assert job.prompt_version
    assert job.output_schema_version


@pytest.mark.asyncio
async def test_ai_job_records_processing_window_and_retry_count() -> None:
    repository = FakeJobRepository()
    job = await create_ai_job(repository, target_type="care_report", target_id=uuid4())

    assert (job.retry_count or 0) == 0
    assert job.started_at is None
    assert job.completed_at is None
    job.started_at = job.created_at
    job.completed_at = job.created_at
    job.retry_count += 1
    assert job.completed_at >= job.started_at
    assert job.retry_count == 1


@pytest.mark.asyncio
async def test_ai_call_uses_the_job_version_snapshot_and_records_times() -> None:
    repository = FakeJobRepository()
    job = await create_ai_job(repository, target_type="care_report", target_id=uuid4())
    adapter = MockAIAdapter(result={"observations": []})

    await AIJobHandler(adapter).handle(
        job,
        note="描述性心得",
        cleaned_images=[],
        allowed_codes=set(),
    )

    request = adapter.requests[0]
    assert request.provider == job.provider
    assert request.model_name == job.model_name
    assert request.model_version == job.model_version
    assert request.prompt_template_id == job.prompt_template_id
    assert request.prompt_version == job.prompt_version
    assert request.output_schema_version == job.output_schema_version
    assert job.started_at is not None
    assert job.completed_at is not None
    assert job.completed_at >= job.started_at


@pytest.mark.asyncio
async def test_ai_timeout_increments_retry_count_without_changing_job_versions() -> None:
    repository = FakeJobRepository()
    job = await create_ai_job(repository, target_type="care_report", target_id=uuid4())

    await AIJobHandler(MockAIAdapter(error=TimeoutError())).handle(
        job,
        note=None,
        cleaned_images=[],
        allowed_codes=set(),
    )

    assert job.status == "failed"
    assert job.retry_count == 1
    assert job.model_version
