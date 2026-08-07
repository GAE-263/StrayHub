import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from jwt import InvalidTokenError
from services.api.app.infrastructure.auth.access_token_adapter import JwtAccessTokenAdapter


def test_access_token_rejects_unknown_key_id() -> None:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    public_pem = (
        private.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
    )
    adapter = JwtAccessTokenAdapter(
        private_key=private_pem,
        public_keys={"active": public_pem},
        issuer="strayhub-test",
        audience="strayhub-api",
    )
    token = adapter.issue({"sub": "user-1"})
    adapter.public_keys = {}

    with pytest.raises(ValueError, match="unknown access token key"):
        adapter.verify(token)


def test_access_token_rejects_algorithm_confusion_and_wrong_issuer() -> None:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    public_pem = (
        private.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
    )
    adapter = JwtAccessTokenAdapter(
        private_key=private_pem,
        public_keys={"active": public_pem},
        issuer="strayhub-test",
        audience="strayhub-api",
    )
    token = adapter.issue({"sub": "user-1"})
    _header, payload, signature = token.split(".")
    import base64

    altered = (
        base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
        + "."
        + payload
        + "."
        + signature
    )
    with pytest.raises((InvalidTokenError, ValueError)):
        adapter.verify(altered)
