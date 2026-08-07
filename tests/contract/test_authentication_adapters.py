from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from services.api.app.application.authentication.session_service import _refresh_digest
from services.api.app.infrastructure.auth.access_token_adapter import JwtAccessTokenAdapter
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher


def _key_pair() -> tuple[str, str]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    public_pem = (
        private.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
    )
    return private_pem, public_pem


def test_argon2id_port_contract() -> None:
    adapter = Argon2PasswordHasher()
    encoded = adapter.hash("correct horse battery staple")

    assert encoded.startswith("$argon2id$")
    assert adapter.verify("correct horse battery staple", encoded)
    assert not adapter.verify("wrong password", encoded)
    assert not adapter.needs_rehash(encoded)


def test_rs256_port_contract_excludes_authorization_scope_claims() -> None:
    private_key, public_key = _key_pair()
    adapter = JwtAccessTokenAdapter(
        private_key=private_key,
        public_keys={"active": public_key},
        issuer="strayhub-test",
        audience="strayhub-api",
        active_kid="active",
    )

    token = adapter.issue({"sub": "user-1", "org_id": "org-a", "role": "STAFF"})
    claims = adapter.verify(token)

    assert claims["sub"] == "user-1"
    assert claims["iss"] == "strayhub-test"
    assert claims["aud"] == "strayhub-api"
    assert claims["typ"] == "access"
    assert "org_id" not in claims
    assert "role" not in claims
    assert claims["exp"] > int(datetime.now(timezone.utc).timestamp())


def test_refresh_token_digest_is_one_way_and_256_bit_input_is_supported() -> None:
    raw = "a" * 64
    digest = _refresh_digest(raw)

    assert len(digest) == 64
    assert raw not in digest
