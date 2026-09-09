import json
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from services.api.app.api.errors import DomainError
from services.api.app.infrastructure.auth.google_identity_verifier import GoogleIdentityVerifier


@pytest.fixture
def signed_identity():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "synthetic-google-test")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()

    def token(**overrides):
        claims = {
            "sub": "test-google-sub",
            "aud": "test.apps.googleusercontent.com",
            "iss": "https://accounts.google.com",
            "iat": int(now.timestamp()),
            "exp": int(now.timestamp()) + 300,
            "nonce": "test-nonce",
        }
        claims.update(overrides)
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "first"})

    return token, pem


@pytest.mark.asyncio
async def test_official_verifier_validates_claims_and_reuses_cache(signed_identity):
    token, pem = signed_identity
    calls = []

    def transport(request):
        calls.append(request.url)
        return httpx.Response(
            200, json={"first": pem}, headers={"cache-control": "public, max-age=60"}
        )

    verifier = GoogleIdentityVerifier(transport=httpx.MockTransport(transport))
    for _ in range(2):
        claims = await verifier.verify(token(), client_id="test.apps.googleusercontent.com")
        assert claims["sub"] == "test-google-sub"
    assert len(calls) == 1
    for overrides in (
        {"aud": "attacker"},
        {"iss": "attacker"},
        {"exp": 1},
        {"iat": 9999999999},
        {"sub": 123},
    ):
        with pytest.raises(DomainError) as error:
            await verifier.verify(token(**overrides), client_id="test.apps.googleusercontent.com")
        assert error.value.status_code == 401
        assert token() not in str(error.value)


@pytest.mark.asyncio
async def test_expired_cache_fails_closed_and_unknown_kid_is_throttled(signed_identity):
    token, pem = signed_identity
    now = [100.0]
    calls = []

    def transport(request):
        calls.append(request)
        if len(calls) > 1:
            raise httpx.ReadTimeout("synthetic")
        return httpx.Response(200, json={"first": pem}, headers={"cache-control": "max-age=20"})

    verifier = GoogleIdentityVerifier(
        transport=httpx.MockTransport(transport), clock=lambda: now[0]
    )
    await verifier.verify(token(), client_id="test.apps.googleusercontent.com")
    parts = token().split(".")
    import base64

    parts[0] = (
        base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "kid": "unknown"}).encode())
        .decode()
        .rstrip("=")
    )
    for _ in range(2):
        with pytest.raises(DomainError):
            await verifier.verify(".".join(parts), client_id="test.apps.googleusercontent.com")
    assert len(calls) == 1
    now[0] += 21
    with pytest.raises(DomainError) as error:
        await verifier.verify(token(), client_id="test.apps.googleusercontent.com")
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_rejects_algorithm_confusion_without_network():
    verifier = GoogleIdentityVerifier()
    token = jwt.encode(
        {"sub": "attacker"}, "synthetic", algorithm="HS256", headers={"kid": "first"}
    )
    with pytest.raises(DomainError) as error:
        await verifier.verify(token, client_id="test.apps.googleusercontent.com")
    assert error.value.status_code == 401
