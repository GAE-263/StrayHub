import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.worker.app.handlers.ai_handler import AIJobHandler
from services.worker.app.infrastructure.mock_ai_adapter import MockAIAdapter


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
@pytest.mark.parametrize("error", [TimeoutError(), ConnectionError(), asyncio.CancelledError()])
async def test_ai_failure_keeps_report_and_timeline_non_normal(error: BaseException) -> None:
    job = _job()
    report = SimpleNamespace(
        id=job.target_id,
        organization_id=job.organization_id,
        answers={"feeding": "feeding.normal"},
        note="志工原始心得",
        status="saved",
        ai_job_status="enqueued",
    )
    result = await AIJobHandler(MockAIAdapter(error=error)).handle(
        job,
        note=report.note,
        cleaned_images=[],
        allowed_codes=set(),
        report=report,
    )

    assert report.answers == {"feeding": "feeding.normal"}
    assert report.note == "志工原始心得"
    assert report.status == "saved"
    assert result.status in {"failed", "invalid"}
    assert report.ai_job_status in {"failed", "invalid"}
    assert report.ai_job_status not in {"normal", "completed", "no_special_signal"}
