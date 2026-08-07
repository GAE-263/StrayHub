from uuid import uuid4

import pytest
from services.api.app.application.ai_job_dispatch import create_ai_job


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
