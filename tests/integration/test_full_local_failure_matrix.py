import base64
import hashlib
import hmac
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from PIL import Image
from services.api.app.api.errors import DomainError
from services.api.app.application.line_postback_service import InMemoryBotDraft, LinePostbackService
from services.api.app.application.media_service import MediaProcessingService
from services.api.app.domain.line_care_report_state import DraftState, DraftStateMachine
from services.api.app.domain.line_webhook_security import verify_line_signature
from services.api.app.infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake
from services.worker.app.handlers.ai_handler import AIJobHandler
from services.worker.app.infrastructure.mock_ai_adapter import MockAIAdapter


def test_full_failure_matrix_rejects_auth_tampering_and_redelivery() -> None:
    body = b'{"events":[]}'
    secret = "local-secret"
    signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    verify_line_signature(raw_body=body, signature=signature, channel_secret=secret)
    with pytest.raises(DomainError, match="簽章"):
        verify_line_signature(raw_body=body, signature="tampered", channel_secret=secret)

    organization_id, volunteer_id = uuid4(), uuid4()
    service = LinePostbackService()
    service.register_draft(
        "local-token",
        InMemoryBotDraft(
            organization_id,
            volunteer_id,
            DraftStateMachine(DraftState.CONFIRMING_ANIMAL),
        ),
    )
    kwargs = {
        "line_user_id": str(volunteer_id),
        "draft_token": "local-token",
        "action": "confirm",
        "organization_id": organization_id,
    }
    assert service.handle(event_id="event-1", **kwargs) == "processed"
    assert service.handle(event_id="event-1", **kwargs) == "duplicate_ignored"
    with pytest.raises(DomainError, match="草稿"):
        service.handle(event_id="event-2", **{**kwargs, "organization_id": uuid4()})


@pytest.mark.asyncio
async def test_full_failure_matrix_keeps_core_data_on_adapter_media_and_ai_failure() -> None:
    class BrokenClient:
        async def post(self, *_args, **_kwargs):
            raise httpx.ConnectError("offline")

    with pytest.raises(DomainError, match="LINE"):
        await LineMessagingApiAdapter(client=BrokenClient()).reply(
            reply_token="reply", messages=[{"type": "text", "text": "ok"}]
        )

    image = BytesIO()
    Image.new("RGB", (2, 2), "red").save(image, format="JPEG")
    with pytest.raises(DomainError, match="實際格式"):
        MediaProcessingService(InMemoryStorageFake()).sanitize(
            image.getvalue(), declared_content_type="image/png"
        )

    organization_id = uuid4()
    report = SimpleNamespace(id=uuid4(), organization_id=organization_id, ai_job_status="saved")
    job = SimpleNamespace(
        organization_id=organization_id,
        target_type="care_report",
        target_id=report.id,
        status="pending",
        provider="mock",
        model_name="local",
        model_version="v1",
        prompt_template_id="care",
        prompt_version="v1",
        output_schema_version="v1",
        raw_ai_output=None,
        validation_result=None,
        failure_reason=None,
        retry_count=0,
    )
    await AIJobHandler(MockAIAdapter(error=TimeoutError())).handle(
        job,
        note="原始心得",
        cleaned_images=[],
        allowed_codes=set(),
        report=report,
    )
    assert job.status == "failed"
    assert report.ai_job_status == "failed"
    assert report.id == job.target_id
