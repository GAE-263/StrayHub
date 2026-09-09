"""Fail-closed credential input for local demo identities."""

from __future__ import annotations

import hashlib
import hmac
import os

DEMO_PASSWORD_ENV = "STRAYHUB_DEMO_PASSWORD"
EXPOSED_DEMO_PASSWORD_SHA256 = "7b7950e2b83458238aab6982317441433d02b7623905be17ad68eeea96d719fa"


def require_demo_password(value: str | None = None) -> str:
    password = value if value is not None else os.environ.get(DEMO_PASSWORD_ENV, "")
    if not password:
        raise ValueError(f"{DEMO_PASSWORD_ENV} is required for demo account provisioning")
    password_digest = hashlib.sha256(password.encode()).hexdigest()
    if hmac.compare_digest(password_digest, EXPOSED_DEMO_PASSWORD_SHA256):
        raise ValueError("exposed demo password is forbidden")
    if len(password) < 16:
        raise ValueError("demo password must be at least 16 characters")
    return password
