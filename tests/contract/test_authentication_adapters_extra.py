import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from services.api.app.infrastructure.auth.access_token_adapter import JwtAccessTokenAdapter
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher


def _pair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return (
        key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode(),
        key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode(),
    )


def test_adapter_supports_previous_key_and_rejects_missing_claims() -> None:
    active_private, active_public = _pair()
    previous_private, previous_public = _pair()
    adapter = JwtAccessTokenAdapter(
        private_key=previous_private,
        public_keys={"previous": previous_public, "active": active_public},
        issuer="issuer",
        audience="audience",
        active_kid="previous",
    )
    token = adapter.issue({"sub": "user", "sid": "session"})
    assert adapter.verify(token)["sub"] == "user"

    unsigned = jwt.encode(
        {"sub": "user", "iss": "issuer", "aud": "audience"},
        key="",
        algorithm="none",
    )
    with pytest.raises((ValueError, jwt.InvalidTokenError)):
        adapter.verify(unsigned)


def test_password_hasher_rehashes_weak_argon2_parameters() -> None:
    hasher = Argon2PasswordHasher()
    weak = (
        "$argon2id$v=19$m=1024,t=2,p=1$YWJjZGVmZ2hpamtsbW5vcA$"
        "w6q8rXg6n5V7sQ3G6aM4d2nY3eM6Y4g0c9q9J7m8n6k"
    )
    assert hasher.needs_rehash(weak)
