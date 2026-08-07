from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any


def sign_line_body(body: bytes, channel_secret: str = "test-secret") -> str:
    digest = hmac.new(channel_secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def postback_event(*, event_id: str = "event-1", value: str = "feeding.normal") -> dict[str, Any]:
    return {
        "destination": "Utest",
        "events": [
            {
                "type": "postback",
                "webhookEventId": event_id,
                "deliveryContext": {"isRedelivery": False},
                "source": {"type": "user", "userId": "Uvolunteer"},
                "postback": {"data": f"action=answer&value={value}"},
            }
        ],
    }


def image_event(*, event_id: str = "image-event-1") -> dict[str, Any]:
    event = postback_event(event_id=event_id)
    event["events"][0] = {
        "type": "message",
        "webhookEventId": event_id,
        "deliveryContext": {"isRedelivery": False},
        "source": {"type": "user", "userId": "Uvolunteer"},
        "message": {"id": "media-1", "type": "image"},
    }
    return event


def body_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()
