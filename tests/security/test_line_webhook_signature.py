import base64
import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient
from services.api.app.api.errors import DomainError
from services.api.app.domain.line_webhook_security import verify_line_signature
from services.api.app.main import app


def test_line_signature_validates_raw_body_before_event_processing() -> None:
    body = b'{"events":[]}'
    secret = "test-secret"
    signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()

    verify_line_signature(raw_body=body, signature=signature, channel_secret=secret)


@pytest.mark.parametrize("signature", [None, "wrong"])
def test_invalid_line_signature_is_rejected(signature: str | None) -> None:
    with pytest.raises(DomainError, match="簽章無效"):
        verify_line_signature(raw_body=b"{}", signature=signature, channel_secret="test-secret")


def test_invalid_signature_endpoint_does_not_parse_or_process_event() -> None:
    response = TestClient(app).post(
        "/v1/line/webhook",
        content=b'{"events":[{"webhookEventId":"must-not-process"}]}',
        headers={"X-Line-Signature": "invalid"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_line_signature"
