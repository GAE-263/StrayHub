import logging
import re
from typing import Any

_SECRET_PATTERN = re.compile(
    r"(token|secret|password|signed[_-]?url|authorization|line[_-]?user[_-]?id|"
    r"entry[_-]?reference|provider[_-]?credential|recipient[_-]?(?:id|identifier))",
    re.I,
)
_SECRET_VALUE_PATTERN = re.compile(
    r"(?P<prefix>bearer\s+|(?:token|secret|password|authorization|signed[_-]?url|"
    r"line[_-]?user[_-]?id|entry[_-]?reference|provider[_-]?credential|"
    r"recipient[_-]?(?:id|identifier))\s*[:=]\s*)"
    r"(?P<value>[^\s,;&]+)",
    re.I,
)
_STANDARD_LOG_RECORD_FIELDS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


def _mask_string(value: str) -> str:
    return _SECRET_VALUE_PATTERN.sub(r"\g<prefix>[REDACTED]", value)


def mask_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SECRET_PATTERN.search(str(key)) else mask_sensitive(item)
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
        message = record.getMessage()
        record.msg = mask_sensitive(message)
        record.args = ()
        for key, value in list(record.__dict__.items()):
            if key not in _STANDARD_LOG_RECORD_FIELDS:
                record.__dict__[key] = mask_sensitive(value)
        return True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(item, SensitiveLogFilter) for item in logger.filters):
        logger.addFilter(SensitiveLogFilter())
    return logger
