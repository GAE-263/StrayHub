from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.ai_review import AIReviewService
from services.api.app.persistence.models.ai_observation import AIObservation
from services.worker.app.handlers.ai_handler import AIJobHandler
from services.worker.app.infrastructure.mock_ai_adapter import MockAIAdapter


class _Repository:
    def __init__(self, observation: AIObservation):
        self.observation = observation

    async def get(self, observation_id):
        return self.observation if observation_id == self.observation.id else None


@pytest.mark.asyncio
async def test_us5_independent_flow_keeps_report_and_review_history_traceable() -> None:
    organization_id = uuid4()
    report_id = uuid4()
    job = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        target_type="care_report",
        target_id=report_id,
        status="pending",
        provider="mock",
        model_name="mock-observation-model",
        model_version="snapshot-local-v1",
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
        answers={"feeding": "feeding.normal"},
        note="原始心得：今天看到毛髮外觀不同",
        status="saved",
        ai_job_status="enqueued",
    )
    observation = AIObservation(
        organization_id=organization_id,
        job_id=job.id,
        source_type="note",
        source_id=report_id,
    )
    observation.id = uuid4()
    raw = {
        "observations": [
            {"code": "appearance.changed", "description": "毛髮外觀不同"}
        ]
    }

    await AIJobHandler(MockAIAdapter(result=raw)).handle(
        job,
        note=report.note,
        cleaned_images=[],
        allowed_codes={"appearance.changed"},
        report=report,
        observation=observation,
    )
    confirmed = await AIReviewService(_Repository(observation)).review(
        observation.id,
        actor_user_id=uuid4(),
        action="confirm",
        reason="工作人員確認描述與原始心得一致",
    )

    assert report.answers == {"feeding": "feeding.normal"}
    assert report.note.startswith("原始心得")
    assert observation.source_type == "note"
    assert observation.raw_ai_output == raw
    assert observation.validated_ai_observation == raw
    assert confirmed.status == "confirmed"
    assert confirmed.human_review_result["reason"]
