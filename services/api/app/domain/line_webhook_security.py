from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass

from services.api.app.api.errors import DomainError


def verify_line_signature(*, raw_body: bytes, signature: str | None, channel_secret: str) -> None:
    if not signature:
        raise DomainError("invalid_line_signature", "LINE Webhook 簽章無效", 401)
    expected = base64.b64encode(
        hmac.new(channel_secret.encode(), raw_body, hashlib.sha256).digest()
    ).decode()
    if not hmac.compare_digest(expected, signature):
        raise DomainError("invalid_line_signature", "LINE Webhook 簽章無效", 401)


@dataclass
class EventIdempotency:
    statuses: dict[str, str]

    def claim(self, webhook_event_id: str) -> bool:
        if webhook_event_id in self.statuses:
            return False
        self.statuses[webhook_event_id] = "processing"
        return True

    def complete(self, webhook_event_id: str, status: str = "processed") -> None:
        if webhook_event_id not in self.statuses:
            raise DomainError("unknown_webhook_event", "Webhook Event 尚未 claim", 409)
        self.statuses[webhook_event_id] = status
