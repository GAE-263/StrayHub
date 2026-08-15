import logging

from services.api.app.observability.logging import get_logger, mask_sensitive


def test_mask_sensitive_redacts_nested_security_and_audit_fields() -> None:
    payload = mask_sensitive(
        {
            "action": "access_denied",
            "error_message": "token=secret-token",
            "authorization": "Bearer bearer-token",
            "audit": {
                "signed_url": "https://storage.example/photo.jpg?token=signed-token",
                "note": "不敏感的狀態摘要",
            },
        }
    )

    rendered = repr(payload)
    assert "secret-token" not in rendered
    assert "bearer-token" not in rendered
    assert "signed-token" not in rendered
    assert payload["authorization"] == "[REDACTED]"
    assert payload["audit"]["note"] == "不敏感的狀態摘要"


def test_logger_filter_redacts_error_message_and_extra_event(caplog) -> None:
    logger = get_logger("strayhub.quality.observability")
    logger.setLevel(logging.INFO)

    with caplog.at_level(logging.INFO, logger=logger.name):
        logger.error(
            "security error token=%s",
            "error-token",
            extra={
                "security_event": {
                    "action": "access_denied",
                    "signed_url": "https://storage.example/file?token=log-token",
                }
            },
        )

    assert "error-token" not in caplog.text
    assert "log-token" not in caplog.text
    assert "[REDACTED]" in caplog.text


def test_volunteer_identity_and_provider_recipient_fields_are_redacted() -> None:
    payload = mask_sensitive(
        {
            "id_token": "id-secret",
            "entry_reference": "entry-secret",
            "line_user_id": "U123",
            "provider_credential": "provider-secret",
            "recipient_identifier": "recipient-secret",
            "safe": "pending",
        }
    )
    assert payload["safe"] == "pending"
    assert set(payload.values()) >= {"[REDACTED]", "pending"}
    assert all(
        secret not in str(payload)
        for secret in (
            "id-secret",
            "entry-secret",
            "U123",
            "provider-secret",
            "recipient-secret",
        )
    )
