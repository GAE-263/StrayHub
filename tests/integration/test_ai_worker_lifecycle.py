from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.ai_observation import AIObservation
from services.worker.app.handlers.ai_handler import AIJobHandler
from services.worker.app.infrastructure.mock_ai_adapter import MockAIAdapter


def job():
    return SimpleNamespace(
        status="pending",
        provider="mock",
        model_name="model",
        model_version="snapshot-1",
        prompt_version="prompt-1",
        output_schema_version="schema-1",
        raw_ai_output=None,
        validation_result=None,
        failure_reason=None,
        retry_count=0,
    )


@pytest.mark.asyncio
async def test_worker_preserves_raw_output_and_uses_job_versions() -> None:
    adapter = MockAIAdapter(result={"observations": []})
    processed = await AIJobHandler(adapter).handle(
        job(), note="觀察", cleaned_images=[], allowed_codes=set()
    )

    assert processed.status == "succeeded"
    assert processed.raw_ai_output == {"observations": []}
    assert adapter.requests[0].model_version == "snapshot-1"


@pytest.mark.asyncio
async def test_ai_failure_does_not_remove_original_report_data() -> None:
    adapter = MockAIAdapter(error=TimeoutError())
    processed = await AIJobHandler(adapter).handle(
        job(), note="原始心得", cleaned_images=[], allowed_codes=set()
    )

    assert processed.status == "failed"
    assert processed.failure_reason == "TimeoutError"


@pytest.mark.asyncio
async def test_ai_handler_separates_raw_and_validated_observation() -> None:
    adapter = MockAIAdapter(result={"observations": [{"code": "feeding.normal"}]})
    observation = AIObservation(
        organization_id=uuid4(),
        job_id=uuid4(),
        source_type="care_report",
        status="pending",
    )
    processed = await AIJobHandler(adapter).handle(
        job(),
        note=None,
        cleaned_images=[],
        allowed_codes={"feeding.normal"},
        observation=observation,
    )

    assert processed.status == "succeeded"
    assert observation.raw_ai_output == {"observations": [{"code": "feeding.normal"}]}
    assert observation.validated_ai_observation == observation.raw_ai_output
    observation.human_review_result = {"action": "correct", "code": "feeding.less"}
    assert observation.raw_ai_output == {"observations": [{"code": "feeding.normal"}]}


@pytest.mark.asyncio
async def test_worker_rejects_cross_tenant_or_unclean_media() -> None:
    organization_id = uuid4()
    ai_job = job()
    ai_job.organization_id = organization_id
    ai_job.target_type = "care_report"
    ai_job.target_id = uuid4()
    report = type("Report", (), {"id": ai_job.target_id, "organization_id": organization_id})()
    media = type(
        "Media",
        (),
        {"organization_id": uuid4(), "exif_removed": True, "status": "processed"},
    )()

    with pytest.raises(DomainError, match="媒體"):
        await AIJobHandler(MockAIAdapter(result={"observations": []})).handle(
            ai_job,
            note=None,
            cleaned_images=[],
            allowed_codes=set(),
            organization_id=organization_id,
            report=report,
            media_assets=[media],
        )
