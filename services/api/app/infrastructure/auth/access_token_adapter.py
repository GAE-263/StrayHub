from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt


class JwtAccessTokenAdapter:
    def __init__(
        self,
        *,
        private_key: str,
        public_keys: dict[str, str],
        issuer: str,
        audience: str,
        ttl_seconds: int = 900,
        active_kid: str = "active",
    ) -> None:
        self.private_key = private_key
        self.public_keys = public_keys
        self.issuer = issuer
        self.audience = audience
        self.ttl_seconds = ttl_seconds
        self.active_kid = active_kid

    def issue(self, claims: dict[str, Any]) -> str:
        now = datetime.now(timezone.utc)
        safe_claims = {
            key: value
            for key, value in claims.items()
            if key not in {"org_id", "organization_id", "role", "membership_id"}
        }
        payload = {
            **safe_claims,
            "sid": safe_claims.get("sid", str(uuid4())),
            "jti": safe_claims.get("jti", str(uuid4())),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=self.ttl_seconds)).timestamp()),
            "iss": self.issuer,
            "aud": self.audience,
            "typ": "access",
        }
        return jwt.encode(
            payload,
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.active_kid, "typ": "JWT"},
        )

    def verify(self, token: str) -> dict[str, Any]:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or header.get("typ") != "JWT":
            raise ValueError("unsupported access token header")
        kid = header.get("kid")
        public_key = self.public_keys.get(kid)
        if not public_key:
            raise ValueError("unknown access token key")
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=self.issuer,
            audience=self.audience,
            leeway=30,
        )
        if payload.get("typ") != "access":
            raise ValueError("unexpected token type")
        return payload
