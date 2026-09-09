from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from PIL import Image
from services.api.app.api.errors import DomainError
from services.api.app.application.line_postback_service import InMemoryBotDraft, LinePostbackService
from services.api.app.application.media_service import MediaProcessingService
from services.api.app.application.report_job_dispatch import ReportJobDispatchService
from services.api.app.domain.line_care_report_state import DraftState, DraftStateMachine
from services.api.app.domain.line_webhook_security import verify_line_signature
from services.api.app.infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake


def test_invalid_signature_and_redelivery_are_rejected_or_deduplicated() -> None:
    with pytest.raises(DomainError, match="簽章"):
        verify_line_signature(raw_body=b"{}", signature="bad", channel_secret="secret")
    service = LinePostbackService()
    volunteer_id = uuid4()
    organization_id = uuid4()
    service.register_draft(
        "local-draft",
        InMemoryBotDraft(
            organization_id, volunteer_id, DraftStateMachine(DraftState.CONFIRMING_ANIMAL)
        ),
    )
    assert (
        service.handle(
            event_id="redelivery",
            line_user_id=str(volunteer_id),
            draft_token="local-draft",
            action="confirm",
            organization_id=organization_id,
        )
        == "processed"
    )
    assert (
        service.handle(
            event_id="redelivery",
            line_user_id=str(volunteer_id),
            draft_token="local-draft",
            action="confirm",
            organization_id=organization_id,
        )
        == "duplicate_ignored"
    )


@pytest.mark.asyncio
async def test_network_media_and_ai_failures_keep_core_data_safe(monkeypatch) -> None:
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

    report = SimpleNamespace(id=uuid4(), organization_id=uuid4(), ai_job_status="saved")

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def begin(self):
            return self

        async def execute(self, _statement, *_args, **_kwargs):
            return SimpleNamespace(scalar_one_or_none=lambda: report)

    async def fail_job(*_args, **_kwargs):
        raise RuntimeError("queue offline")

    monkeypatch.setattr("services.api.app.application.report_job_dispatch.create_ai_job", fail_job)
    service = ReportJobDispatchService(lambda: Session(), ai_enabled=True)
    assert (
        await service.dispatch(organization_id=report.organization_id, report_id=report.id) is False
    )
