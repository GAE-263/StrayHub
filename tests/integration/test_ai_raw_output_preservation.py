from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.ai_review import AIReviewService
from services.api.app.persistence.models.ai_observation import AIObservation
from services.worker.app.handlers.ai_handler import AIJobHandler
from services.worker.app.infrastructure.ai_port import AIAnalysisEnvelope
from services.worker.app.infrastructure.mock_ai_adapter import MockAIAdapter


@pytest.mark.asyncio
async def test_provider_envelope_preserves_raw_but_validates_only_formal_output() -> None:
    ai_job = _job()
    raw = {"score": 3, "recommendation": "raw review only"}
    formal = {"observations": []}

    processed = await AIJobHandler(
        MockAIAdapter(result=AIAnalysisEnvelope(raw=raw, formal=formal))
    ).handle(ai_job, note=None, cleaned_images=[b"stool"], allowed_codes=set())

    assert processed.status == "succeeded"
    assert processed.raw_ai_output == raw
    assert processed.validation_result == {"status": "valid"}


def _job() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
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
async def test_valid_output_keeps_raw_and_validated_values_separate() -> None:
    job = _job()
    raw = {"observations": [{"code": "appearance.changed", "description": "毛髮外觀不同"}]}
    observation = AIObservation(
        organization_id=job.organization_id,
        job_id=job.id,
        source_type="note",
        source_id=job.target_id,
    )

    await AIJobHandler(MockAIAdapter(result=raw)).handle(
        job,
        note="原始心得",
        cleaned_images=[],
        allowed_codes={"appearance.changed"},
        observation=observation,
        report=SimpleNamespace(id=job.target_id, organization_id=job.organization_id),
    )

    assert job.raw_ai_output == raw
    assert observation.raw_ai_output == raw
    assert observation.validated_ai_observation == raw
    assert observation.human_review_result is None
    assert job.validation_result["status"] == "valid"


@pytest.mark.asyncio
async def test_invalid_output_is_preserved_but_never_becomes_validated() -> None:
    job = _job()
    raw = {"animal_id": "animal-from-model", "observations": []}
    observation = AIObservation(
        organization_id=job.organization_id,
        job_id=job.id,
        source_type="note",
        source_id=job.target_id,
    )

    await AIJobHandler(MockAIAdapter(result=raw)).handle(
        job,
        note="原始心得",
        cleaned_images=[],
        allowed_codes=set(),
        observation=observation,
    )

    assert job.status == "invalid"
    assert observation.status == "invalid"
    assert job.raw_ai_output == raw
    assert observation.raw_ai_output == raw
    assert observation.validated_ai_observation is None
    assert job.validation_result["status"] == "invalid"


@pytest.mark.asyncio
async def test_human_correction_does_not_overwrite_raw_output() -> None:
    job = _job()
    raw = {"observations": [{"code": "appearance.changed"}]}
    observation = AIObservation(
        organization_id=job.organization_id,
        job_id=job.id,
        source_type="note",
        source_id=job.target_id,
    )
    await AIJobHandler(MockAIAdapter(result=raw)).handle(
        job,
        note="原始心得",
        cleaned_images=[],
        allowed_codes={"appearance.changed"},
        observation=observation,
    )

    original = observation.raw_ai_output

    class Repository:
        async def get(self, observation_id):
            return observation if observation_id == observation.id else None

    result = await AIReviewService(Repository()).review(
        observation.id,
        actor_user_id=uuid4(),
        action="correct",
        result={"observations": [{"code": "appearance.other", "description": "人工修正"}]},
        reason="工作人員核對照片後修正",
    )

    assert result.raw_ai_output == original
