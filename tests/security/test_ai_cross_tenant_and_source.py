from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.worker.app.handlers.ai_handler import AIJobHandler
from services.worker.app.infrastructure.mock_ai_adapter import MockAIAdapter


def _job(organization_id):
    return SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        target_type="care_report",
        target_id=uuid4(),
        status="pending",
        provider="mock",
        model_name="model",
        model_version="snapshot-1",
        prompt_template_id="care-observation",
        prompt_version="prompt-1",
        output_schema_version="schema-1",
        raw_ai_output=None,
        validation_result=None,
        failure_reason=None,
        retry_count=0,
    )


@pytest.mark.asyncio
async def test_worker_rejects_cross_tenant_report_before_provider_call() -> None:
    organization_id = uuid4()
    job = _job(organization_id)
    adapter = MockAIAdapter(result={"observations": []})

    with pytest.raises(DomainError, match="目前收容所"):
        await AIJobHandler(adapter).handle(
            job,
            note="心得",
            cleaned_images=[],
            allowed_codes=set(),
            organization_id=uuid4(),
        )
    assert adapter.requests == []


@pytest.mark.asyncio
async def test_worker_rejects_other_tenant_media_and_original_exif() -> None:
    organization_id = uuid4()
    job = _job(organization_id)
    report = SimpleNamespace(id=job.target_id, organization_id=organization_id)
    other_tenant_media = SimpleNamespace(
        id=uuid4(), organization_id=uuid4(), exif_removed=True, status="processed"
    )

    with pytest.raises(DomainError, match="媒體"):
        await AIJobHandler(MockAIAdapter()).handle(
            job,
            note=None,
            cleaned_images=[b"cleaned"],
            allowed_codes=set(),
            report=report,
            media_assets=[other_tenant_media],
        )

    same_tenant_raw_media = SimpleNamespace(
        id=uuid4(), organization_id=organization_id, exif_removed=False, status="processed"
    )
    with pytest.raises(DomainError, match="清理"):
        await AIJobHandler(MockAIAdapter()).handle(
            job,
            note=None,
            cleaned_images=[b"raw"],
            allowed_codes=set(),
            report=report,
            media_assets=[same_tenant_raw_media],
        )


@pytest.mark.asyncio
async def test_successful_observation_has_note_or_cleaned_photo_source() -> None:
    organization_id = uuid4()
    job = _job(organization_id)
    report = SimpleNamespace(id=job.target_id, organization_id=organization_id)
    media = SimpleNamespace(
        id=uuid4(), organization_id=organization_id, exif_removed=True, status="attached"
    )
    observation = SimpleNamespace(source_type=None, source_id=None, status="pending")

    await AIJobHandler(MockAIAdapter(result={"observations": []})).handle(
        job,
        note=None,
        cleaned_images=[b"cleaned"],
        allowed_codes=set(),
        observation=observation,
        report=report,
        media_assets=[media],
    )

    assert observation.source_type == "photo"
    assert observation.source_id == media.id
