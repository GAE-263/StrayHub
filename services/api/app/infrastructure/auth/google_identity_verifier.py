"""Google verification with bounded network work and a process-wide certificate cache."""

import asyncio
import json
import re
import time
from types import SimpleNamespace

import httpx
import jwt
from google.auth.exceptions import GoogleAuthError
from google.oauth2 import id_token

from services.api.app.api.errors import DomainError

CERTS_URL = "https://www.googleapis.com/oauth2/v1/certs"


class GoogleIdentityVerifier:
    def __init__(self, *, transport=None, clock=time.monotonic):
        self.transport = transport
        self.clock = clock
        self.certificates: dict[str, str] = {}
        self.expires_at = 0.0
        self.last_fetch = float("-inf")
        self.lock = asyncio.Lock()
        self.workers = asyncio.Semaphore(8)

    async def _certificates(self, kid: str) -> dict[str, str]:
        async with self.lock:
            now = self.clock()
            if self.expires_at > now and kid in self.certificates:
                return self.certificates.copy()
            if now - self.last_fetch < 10:
                if self.expires_at <= now:
                    raise DomainError("google_unavailable", "Google 登入暫時無法使用", 503)
                return self.certificates.copy()
            self.last_fetch = now
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(3, connect=2),
                    transport=self.transport,
                    follow_redirects=False,
                ) as client:
                    async with client.stream("GET", CERTS_URL) as response:
                        response.raise_for_status()
                        data = bytearray()
                        async for chunk in response.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > 131072:
                                raise ValueError
                        certificates = json.loads(data)
                        if (
                            not isinstance(certificates, dict)
                            or not certificates
                            or not all(
                                isinstance(k, str) and isinstance(v, str)
                                for k, v in certificates.items()
                            )
                        ):
                            raise ValueError
                        cache_control = response.headers.get("cache-control", "")
                        match = re.search(r"(?:^|[,\s])max-age=(\d+)", cache_control)
                        age = max(0, int(response.headers.get("age", "0")))
                        ttl = max(0, min(int(match[1]), 86400) - age) if match else 0
                        if "no-store" in cache_control or "no-cache" in cache_control:
                            ttl = 0
                        self.certificates = certificates
                        self.expires_at = self.clock() + ttl
                        return certificates.copy()
            except (httpx.HTTPError, ValueError, TypeError):
                raise DomainError("google_unavailable", "Google 登入暫時無法使用", 503) from None

    async def verify(self, token: str, *, client_id: str) -> dict:
        try:
            if not client_id or len(token) > 8192:
                raise ValueError
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise ValueError
            async with asyncio.timeout(7):
                certificates = await self._certificates(header["kid"])
                if header["kid"] not in certificates:
                    raise ValueError

                # Official verifier sees only the fixed, already-fetched PEM cache.
                # Its synchronous request callback cannot make network requests.
                def cached_request(url, **_kwargs):
                    if url != CERTS_URL:
                        raise ValueError
                    return SimpleNamespace(status=200, data=json.dumps(certificates).encode())

                async with self.workers:
                    claims = await asyncio.to_thread(
                        id_token.verify_oauth2_token, token, cached_request, client_id
                    )
            if (
                not isinstance(claims.get("sub"), str)
                or not 1 <= len(claims["sub"]) <= 255
                or not isinstance(claims.get("nonce"), str)
                or not isinstance(claims.get("iat"), (int, float))
                or not isinstance(claims.get("exp"), (int, float))
                or claims.get("aud") != client_id
            ):
                raise ValueError
            return claims
        except TimeoutError:
            raise DomainError("google_unavailable", "Google 登入暫時無法使用", 503) from None
        except (ValueError, TypeError, KeyError, GoogleAuthError, jwt.PyJWTError):
            raise DomainError("invalid_google_token", "Google 身分驗證失敗", 401) from None


google_identity_verifier = GoogleIdentityVerifier()
