import logging
import re
import traceback
from typing import Any
from urllib.parse import unquote

_EXACT_SENSITIVE_KEYS = {
    "authorization",
    "password",
    "temporary_password",
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "qr_token",
    "entry",
    "entry_reference",
    "shelter_entry_reference",
    "signed_url",
    "api_key",
    "api_secret",
    "client_secret",
    "provider_secret",
    "provider_credential",
    "signature",
    "line_channel_secret",
    "line_channel_access_token",
    "line_user_id",
    "recipient_id",
    "recipient_identifier",
}
_SENSITIVE_SUFFIXES = ("_password", "_secret", "_token", "_credential", "_signature")
_COLLAPSED_SENSITIVE_KEYS = {key.replace("_", "") for key in _EXACT_SENSITIVE_KEYS}
_BEARER_PATTERN = re.compile(r"(?P<prefix>\bbearer\s+)(?P<value>[^\s,;&]+)", re.I)
_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?P<prefix>[\"']?(?P<key>(?:[A-Za-z0-9_.-]*(?:password|secret|token|credential|signature)|"
    r"authorization|entry|signed[_-]?url|line[_-]?user[_-]?id|"
    r"recipient[_-]?(?:id|identifier)))[\"']?\s*[:=]\s*[\"']?)"
    r"(?P<value>[^\"'\s,;&}\]]+)",
    re.I,
)
_STANDARD_LOG_RECORD_FIELDS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


def _normalize_key(value: str) -> str:
    return unquote(value).casefold().replace("-", "_")


def _is_sensitive_key(value: str) -> bool:
    normalized = _normalize_key(value)
    return (
        normalized in _EXACT_SENSITIVE_KEYS
        or normalized.replace("_", "") in _COLLAPSED_SENSITIVE_KEYS
        or normalized.endswith(_SENSITIVE_SUFFIXES)
    )


def _redact_assignments(value: str) -> str:
    redacted = _BEARER_PATTERN.sub(r"\g<prefix>[REDACTED]", value)
    return _SENSITIVE_ASSIGNMENT_PATTERN.sub(r"\g<prefix>[REDACTED]", redacted)


def _mask_string(value: str) -> str:
    decoded = value
    for _ in range(2):
        candidate = unquote(decoded)
        if candidate == decoded:
            break
        decoded = candidate
    decoded_redacted = _redact_assignments(decoded)
    if decoded_redacted != decoded:
        return decoded_redacted
    return _redact_assignments(value)


def mask_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _is_sensitive_key(str(key)) else mask_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [mask_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(mask_sensitive(item) for item in value)
    if isinstance(value, str):
        return _mask_string(value)
    return value


class SensitiveLogFilter(logging.Filter):
    """Mask structured fields and formatted messages before any handler emits them."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "uvicorn.access" and isinstance(record.args, tuple):
            # Uvicorn's AccessFormatter unpacks five positional fields from args.
            # Sanitize those values without flattening the record structure.
            record.msg = mask_sensitive(record.msg)
            record.args = mask_sensitive(record.args)
        else:
            message = record.getMessage()
            record.msg = mask_sensitive(message)
            record.args = ()
        for key, value in list(record.__dict__.items()):
            if key not in _STANDARD_LOG_RECORD_FIELDS:
                record.__dict__[key] = (
                    "[REDACTED]" if _is_sensitive_key(key) else mask_sensitive(value)
                )
        if record.exc_info:
            record.exc_text = mask_sensitive("".join(traceback.format_exception(*record.exc_info)))
            record.exc_info = None
        return True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(item, SensitiveLogFilter) for item in logger.filters):
        logger.addFilter(SensitiveLogFilter())
    return logger


def configure_access_log_redaction() -> None:
    """Apply the sensitive-value policy to Uvicorn access and server errors."""
    get_logger("uvicorn.access")
    get_logger("uvicorn.error")
