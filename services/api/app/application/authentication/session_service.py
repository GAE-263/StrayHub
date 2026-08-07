from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from services.api.app.api.errors import DomainError
from services.api.app.application.ports.authentication import (
    AccessTokenPort,
    LineIdentityVerifierPort,
    PasswordHasherPort,
)
from services.api.app.persistence.models.identity import RefreshTokenRecord, SessionRecord
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)


def _refresh_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SessionService:
    def __init__(
        self,
        repository: AuthenticationRepository,
        *,
        password_hasher: PasswordHasherPort,
        access_token: AccessTokenPort,
        line_verifier: LineIdentityVerifierPort | None = None,
        refresh_ttl_seconds: int = 604800,
        access_ttl_seconds: int = 900,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher
        self.access_token = access_token
        self.line_verifier = line_verifier
        self.refresh_ttl_seconds = refresh_ttl_seconds
        self.access_ttl_seconds = access_ttl_seconds

    async def login(self, *, username: str, password: str) -> dict:
        user = await self.repository.find_user_by_username(username)
        if user is None or user.status != "active" or not user.password_hash:
            raise DomainError("invalid_credentials", "帳號或密碼錯誤", 401)
        if not self.password_hasher.verify(password, user.password_hash):
            raise DomainError("invalid_credentials", "帳號或密碼錯誤", 401)
        if self.password_hasher.needs_rehash(user.password_hash):
            user.password_hash = self.password_hasher.hash(password)
        session = SessionRecord(
            user_id=user.id,
            status="active",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.refresh_ttl_seconds),
        )
        await self.repository.add(session)
        return await self._issue_session(user.id, session)

    async def refresh(self, *, refresh_token: str) -> dict:
        record = await self.repository.get_refresh_token(_refresh_digest(refresh_token))
        now = datetime.now(timezone.utc)
        if record is None or record.status != "active" or record.expires_at <= now:
            if record is not None:
                await self.repository.revoke_refresh_family(record.family_id)
            raise DomainError("invalid_refresh_token", "Refresh Token 無效", 401)
        session = await self.repository.get_session(record.session_id)
        user = session and await self.repository.get_user(session.user_id)
        if session is None or user is None or session.status != "active" or user.status != "active":
            raise DomainError("invalid_session", "Session 無效", 401)
        record.status = "rotated"
        return await self._issue_session(user.id, session, family_id=record.family_id)

    async def logout(self, *, session_id: UUID) -> None:
        session = await self.repository.get_session(session_id)
        if session:
            session.status = "revoked"
            # Revoking the server-side session must also invalidate every refresh
            # token family attached to it; access tokens are checked against this
            # record on every protected request.
            records = await self.repository.refresh_tokens_for_session(session_id)
            for record in records:
                record.status = "revoked"

    async def current_user(self, *, session_id: UUID) -> dict:
        session = await self.repository.get_session(session_id)
        if (
            session is None
            or session.status != "active"
            or session.expires_at <= datetime.now(timezone.utc)
        ):
            raise DomainError("invalid_session", "Session 無效", 401)
        user = await self.repository.get_user(session.user_id)
        if user is None or user.status != "active":
            raise DomainError("invalid_session", "使用者無效", 401)
        return {
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "platform_role": user.platform_role,
                "status": user.status,
            },
            "memberships": [
                {
                    "id": membership.id,
                    "organization_id": membership.organization_id,
                    "role": membership.role,
                    "status": membership.status,
                }
                for membership in await self.repository.memberships(user.id)
            ],
        }

    async def exchange_line_identity(self, *, id_token: str) -> dict:
        if self.line_verifier is None:
            raise DomainError("line_not_configured", "LINE 身分驗證尚未設定", 503)
        line_user_id = await self.line_verifier.verify(id_token)
        binding = await self.repository.get_line_binding(line_user_id)
        if binding is None:
            raise DomainError("line_binding_required", "請先完成 LINE 身分綁定", 403)
        user = await self.repository.get_user(binding.user_id)
        if user is None or user.status != "active":
            raise DomainError("line_binding_invalid", "LINE 身分綁定無效", 403)
        memberships = await self.repository.memberships(user.id, active_only=True)
        if len(memberships) != 1:
            raise DomainError("shelter_context_required", "請在 LIFF 明確選擇收容所", 409)
        organization = await self.repository.get_organization(memberships[0].organization_id)
        if organization is None or organization.status != "active":
            raise DomainError("organization_disabled", "收容所目前停用", 403)
        session = SessionRecord(
            user_id=user.id,
            active_organization_id=organization.id,
            status="active",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.refresh_ttl_seconds),
        )
        await self.repository.add(session)
        return await self._issue_session(user.id, session)

    async def _issue_session(
        self, user_id: UUID, session: SessionRecord, *, family_id: UUID | None = None
    ) -> dict:
        refresh_token = secrets.token_bytes(32).hex()
        refresh_record = RefreshTokenRecord(
            session_id=session.id,
            token_digest=_refresh_digest(refresh_token),
            family_id=family_id or uuid4(),
            status="active",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.refresh_ttl_seconds),
        )
        await self.repository.add(refresh_record)
        token = self.access_token.issue({"sub": str(user_id), "sid": str(session.id)})
        return {
            "access_token": token,
            "refresh_token": refresh_token,
            "expires_in": self.access_ttl_seconds,
            "session_id": session.id,
            "user_id": user_id,
        }
