from __future__ import annotations

import hashlib
import hmac
import ipaddress
import unicodedata
from dataclasses import dataclass

from pydantic import SecretStr

ACCOUNT_FAILURE_LIMIT = 5
ACCOUNT_LOCK_SECONDS = 900
IP_ATTEMPT_LIMIT = 20
IP_WINDOW_SECONDS = 900


class LoginAbuseKeys:
    def __init__(self, secret: SecretStr) -> None:
        value = secret.get_secret_value().encode("utf-8")
        if len(value) < 24:
            raise ValueError("login abuse HMAC secret is too short")
        self._secret = value

    def _digest(self, domain: str, value: str) -> str:
        return hmac.new(
            self._secret,
            f"{domain}:{value}".encode(),
            hashlib.sha256,
        ).hexdigest()

    def account_digest(self, username: str) -> str:
        normalized = unicodedata.normalize("NFKC", username).strip().casefold()
        return self._digest("account", normalized)

    def ip_digest(self, client_ip: str) -> str:
        normalized = str(ipaddress.ip_address(client_ip))
        return self._digest("ip", normalized)


@dataclass(frozen=True)
class LoginLimitDecision:
    allowed: bool
    retry_after: int | None = None
