from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.ai_review import AIReviewService
from services.api.app.persistence.models.ai_observation import AIObservation
from services.worker.app.handlers.ai_handler import AIJobHandler
from services.worker.app.infrastructure.mock_ai_adapter import MockAIAdapter


class _ObservationRepository:
    def __init__(self, observation: AIObservation) -> None:
        self.observation = observation

    async def get(self, observation_id):
        if observation_id == self.observation.id:
            return self.observation
        return None


@pytest.mark.asyncio
async def test_full_local_flow_reaches_human_review_after_real_bot_flow() -> None:
    """Run the real PostgreSQL vertical flow, then complete its local AI boundary."""
    from services.api.app.persistence.database.engine import engine

    from tests.e2e.test_local_line_bot_vertical_flow import (
        test_local_vertical_flow_reaches_report_and_timeline_without_ai_worker,
    )

    try:
        await test_local_vertical_flow_reaches_report_and_timeline_without_ai_worker()
    finally:
        # The wrapped test runs inside this function's event loop. Clear pooled
        # asyncpg connections before pytest gives the next test a new loop.
        await engine.dispose()

    organization_id = uuid4()
    report_id = uuid4()
    job = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        target_type="care_report",
        target_id=report_id,
        status="pending",
        provider="mock",
        model_name="local-observation-model",
        model_version="local-v1",
        prompt_template_id="care-observation",
        prompt_version="local-v1",
        output_schema_version="v1",
        raw_ai_output=None,
        validation_result=None,
        failure_reason=None,
        retry_count=0,
    )
    report = SimpleNamespace(
        id=report_id,
        organization_id=organization_id,
        note="毛髮外觀有變化",
        answers={"feeding": "feeding.normal"},
        ai_job_status="enqueued",
    )
    observation = AIObservation(
        organization_id=organization_id,
        job_id=job.id,
        source_type="note",
        source_id=report_id,
    )
    observation.id = uuid4()
    raw = {"observations": [{"code": "appearance.changed", "description": "毛髮外觀有變化"}]}

    await AIJobHandler(MockAIAdapter(result=raw)).handle(
        job,
        note=report.note,
        cleaned_images=[],
        allowed_codes={"appearance.changed"},
        observation=observation,
        report=report,
    )
    reviewed = await AIReviewService(_ObservationRepository(observation)).review(
        observation.id,
        actor_user_id=uuid4(),
        action="confirm",
        reason="本機工作人員確認",
    )

    assert job.status == "succeeded"
    assert report.answers == {"feeding": "feeding.normal"}
    assert report.ai_job_status == "succeeded"
    assert observation.raw_ai_output == raw
    assert observation.validated_ai_observation == raw
    assert reviewed.status == "confirmed"
