import logging
import re
from typing import Any

_SECRET_PATTERN = re.compile(r"(token|secret|password|signed[_-]?url|authorization)", re.I)


def mask_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SECRET_PATTERN.search(key) else mask_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [mask_sensitive(item) for item in value]
    return value


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
