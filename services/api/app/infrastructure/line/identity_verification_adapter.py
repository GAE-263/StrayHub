from datetime import datetime, timezone

import httpx

from services.api.app.api.errors import DomainError


class MockLineIdentityVerifier:
    """Resolve deterministic local-only identity tokens without calling LINE."""

    prefix = "local-id-token:"

    async def verify(self, token: str) -> str:
        if not token or not token.startswith(self.prefix):
            raise ValueError("local LINE identity token is invalid")
        subject = token.removeprefix(self.prefix)
        if not subject:
            raise ValueError("local LINE identity token has no subject")
        return subject if subject.startswith("U") else f"U{subject}"


def configured_line_identity_verifier(*, app_env: str, channel_id: str):
    """Use mock identity only for the repository's fake local LINE configuration."""

    if app_env == "local" and channel_id.startswith("fake-"):
        return MockLineIdentityVerifier()
    return LineIdentityVerifier(channel_id)


class LineIdentityVerifier:
    def __init__(self, channel_id: str, *, client: httpx.AsyncClient | None = None) -> None:
        self.channel_id = channel_id
        self.client = client

    async def verify(self, token: str) -> str:
        if not token:
            raise DomainError("invalid_line_id_token", "無法確認 LINE 身分", 401)
        client = self.client or httpx.AsyncClient()
        try:
            response = await client.post(
                "https://api.line.me/oauth2/v2.1/verify",
                data={"id_token": token, "client_id": self.channel_id},
            )
            if response.status_code >= 500:
                raise DomainError(
                    "line_identity_provider_unavailable",
                    "LINE 身分服務暫時無法使用",
                    503,
                )
            if not response.is_success:
                raise DomainError("invalid_line_id_token", "無法確認 LINE 身分", 401)
            claims = response.json()
            expires_at = claims.get("exp")
            now = int(datetime.now(timezone.utc).timestamp())
            if (
                claims.get("iss") != "https://access.line.me"
                or claims.get("aud") != self.channel_id
                or not isinstance(expires_at, int)
                or expires_at <= now
                or not isinstance(claims.get("sub"), str)
                or not claims["sub"]
            ):
                raise DomainError("invalid_line_id_token", "無法確認 LINE 身分", 401)
            return claims["sub"]
        except DomainError:
            raise
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise DomainError(
                "line_identity_provider_unavailable",
                "LINE 身分服務暫時無法使用",
                503,
            ) from exc
        finally:
            if self.client is None:
                await client.aclose()
