import io
import logging
from copy import deepcopy

import pytest
from services.api.app.observability.logging import (
    SensitiveLogFilter,
    configure_access_log_redaction,
    get_logger,
    mask_sensitive,
)
from uvicorn.logging import AccessFormatter


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


@pytest.mark.parametrize(
    "path",
    [
        "/v1/public/animals/abc/photo?token=ANIMAL-CAPABILITY-SECRET",
        "/v1/public/adoption/animals/abc/photo?token=ADOPTION-CAPABILITY-SECRET",
    ],
)
def test_uvicorn_access_logger_redacts_photo_capabilities(path: str) -> None:
    logger = logging.getLogger("uvicorn.access")
    original_handlers = logger.handlers[:]
    original_filters = logger.filters[:]
    original_level = logger.level
    original_propagate = logger.propagate
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s'))
    try:
        logger.handlers = [handler]
        logger.filters = []
        logger.setLevel(logging.INFO)
        logger.propagate = False

        configure_access_log_redaction()
        logger.info(
            '%s - "%s %s HTTP/%s" %d',
            "127.0.0.1:12345",
            "GET",
            path,
            "1.1",
            200,
        )

        rendered = output.getvalue()
        assert "CAPABILITY-SECRET" not in rendered
        assert "token=[REDACTED]" in rendered
        assert sum(isinstance(item, SensitiveLogFilter) for item in logger.filters) == 1
    finally:
        logger.handlers = original_handlers
        logger.filters = original_filters
        logger.setLevel(original_level)
        logger.propagate = original_propagate


def test_uvicorn_access_logger_preserves_ordinary_query_logging() -> None:
    logger = logging.getLogger("uvicorn.access")
    original_handlers = logger.handlers[:]
    original_filters = logger.filters[:]
    original_level = logger.level
    original_propagate = logger.propagate
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s'))
    try:
        logger.handlers = [handler]
        logger.filters = []
        logger.setLevel(logging.INFO)
        logger.propagate = False

        configure_access_log_redaction()
        logger.info(
            '%s - "%s %s HTTP/%s" %d',
            "127.0.0.1:12345",
            "GET",
            "/v1/animals?page=2",
            "1.1",
            200,
        )

        assert "/v1/animals?page=2" in output.getvalue()
    finally:
        logger.handlers = original_handlers
        logger.filters = original_filters
        logger.setLevel(original_level)
        logger.propagate = original_propagate


def test_application_bootstrap_attaches_uvicorn_access_filter() -> None:
    from services.api.app import main

    assert main.app is not None
    assert any(
        isinstance(item, SensitiveLogFilter) for item in logging.getLogger("uvicorn.access").filters
    )
    assert any(
        isinstance(item, SensitiveLogFilter) for item in logging.getLogger("uvicorn.error").filters
    )


def test_mask_sensitive_handles_case_variants_lists_repeated_and_encoded_urls() -> None:
    sentinel_values = (
        "mixed-password-secret",
        "first-id-secret",
        "second-id-secret",
        "nested-access-secret",
        "authorization-secret",
        "storage-signature-secret",
        "camel-access-secret",
    )
    payload = {
        "Temporary-Password": sentinel_values[0],
        "events": [
            {
                "url": (
                    "https://example.test/login?%69d_token=first-id-secret"
                    "&ID_TOKEN=second-id-secret&page=2"
                )
            },
            {
                "next": (
                    "https%3A%2F%2Fexample.test%2Fcallback%3Faccess_token%3D"
                    "nested-access-secret%26status%3Dpending"
                )
            },
            {
                "url": (
                    "https://storage.example/photo?X-Amz-Algorithm=AWS4-HMAC-SHA256"
                    "&X-Amz-Signature=storage-signature-secret"
                )
            },
        ],
        "headers": {"AUTHORIZATION": "Bearer authorization-secret"},
        "AccessToken": "camel-access-secret",
    }
    original = deepcopy(payload)

    masked = mask_sensitive(payload)
    rendered = repr(masked)

    assert payload == original
    assert all(value not in rendered for value in sentinel_values)
    assert "page=2" in rendered
    assert "status" in rendered
    assert rendered.count("[REDACTED]") >= 5


def test_exception_traceback_is_redacted_without_losing_diagnostic_type() -> None:
    logger = get_logger("strayhub.quality.exception")
    original_handlers = logger.handlers[:]
    original_propagate = logger.propagate
    original_level = logger.level
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    try:
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.INFO)
        try:
            raise RuntimeError("password=exception-sentinel-secret")
        except RuntimeError:
            logger.exception("provider request failed")

        rendered = output.getvalue()
        assert "exception-sentinel-secret" not in rendered
        assert "RuntimeError" in rendered
        assert "provider request failed" in rendered
        assert "[REDACTED]" in rendered
    finally:
        logger.handlers = original_handlers
        logger.propagate = original_propagate
        logger.setLevel(original_level)


def test_uvicorn_access_logger_decodes_sensitive_keys_and_preserves_safe_query() -> None:
    logger = logging.getLogger("uvicorn.access")
    original_handlers = logger.handlers[:]
    original_filters = logger.filters[:]
    original_level = logger.level
    original_propagate = logger.propagate
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s'))
    try:
        logger.handlers = [handler]
        logger.filters = []
        logger.setLevel(logging.INFO)
        logger.propagate = False
        configure_access_log_redaction()
        logger.info(
            '%s - "%s %s HTTP/%s" %d',
            "127.0.0.1:12345",
            "GET",
            "/login?%70assword=encoded-secret&id_token=one&id_token=two&page=2",
            "1.1",
            200,
        )

        rendered = output.getvalue()
        assert "encoded-secret" not in rendered
        assert "id_token=one" not in rendered
        assert "id_token=two" not in rendered
        assert "page=2" in rendered
    finally:
        logger.handlers = original_handlers
        logger.filters = original_filters
        logger.setLevel(original_level)
        logger.propagate = original_propagate


def test_raw_application_logger_modules_are_attached_to_central_filter() -> None:
    from services.api.app.api import line_webhook, management_animals
    from services.worker import worker
    from services.worker.app.handlers import volunteer_access_handler

    for module in (line_webhook, management_animals, worker, volunteer_access_handler):
        assert any(isinstance(item, SensitiveLogFilter) for item in module.logger.filters)
