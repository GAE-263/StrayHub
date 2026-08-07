from services.api.app.domain.line_webhook_security import EventIdempotency


def test_redelivery_claim_is_idempotent() -> None:
    events = EventIdempotency({})

    assert events.claim("event-1")
    assert not events.claim("event-1")
    events.complete("event-1")
    assert events.statuses["event-1"] == "processed"
