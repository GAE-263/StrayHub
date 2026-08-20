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
    VolunteerEntryResolverPort,
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
        entry_resolver: VolunteerEntryResolverPort | None = None,
        refresh_ttl_seconds: int = 604800,
        access_ttl_seconds: int = 900,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher
        self.access_token = access_token
        self.line_verifier = line_verifier
        self.entry_resolver = entry_resolver
        self.refresh_ttl_seconds = refresh_ttl_seconds
        self.access_ttl_seconds = access_ttl_seconds

    async def login(self, *, username: str, password: str) -> dict:
        user = await self.repository.find_user_by_username(username)
        if user is None or user.status != "active" or not user.password_hash:
            raise DomainError("invalid_credentials", "帳號或密碼錯誤", 401)
        if not self.password_hasher.verify(password, user.password_hash):
            raise DomainError("invalid_credentials", "帳號或密碼錯誤", 401)
        await self.repository.set_authentication_user_scope(user.id)
        if user.platform_role != "PLATFORM_ADMIN" and not await self._has_active_shelter_access(
            user.id
        ):
            raise DomainError("invalid_credentials", "帳號或密碼錯誤", 401)
        if self.password_hasher.needs_rehash(user.password_hash):
            user.password_hash = self.password_hasher.hash(password)
        session = SessionRecord(
            user_id=user.id,
            status="active",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.refresh_ttl_seconds),
        )
        await self.repository.add(session)
        result = await self._issue_session(user.id, session)
        result["organizations"] = await self._available_organizations(
            user.id, platform_scope=user.platform_role == "PLATFORM_ADMIN"
        )
        return result

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
        await self.repository.set_authentication_user_scope(user.id)
        if user.platform_role != "PLATFORM_ADMIN" and not await self._has_active_shelter_access(
            user.id
        ):
            raise DomainError("invalid_session", "Session 無效", 401)
        record.status = "rotated"
        return await self._issue_session(user.id, session, family_id=record.family_id)

    async def _has_active_shelter_access(self, user_id: UUID) -> bool:
        for membership in await self.repository.memberships(user_id, active_only=True):
            organization = await self.repository.get_organization(membership.organization_id)
            if organization is not None and organization.status == "active":
                return True
        return False

    async def _available_organizations(
        self, user_id: UUID, *, platform_scope: bool = False
    ) -> list[dict]:
        if platform_scope:
            return [
                {
                    "id": organization.id,
                    "code": organization.code,
                    "name": organization.name,
                    "role": "PLATFORM_ADMIN",
                }
                for organization in await self.repository.organizations(active_only=True)
            ]
        organizations = []
        for membership in await self.repository.memberships(user_id, active_only=True):
            organization = await self.repository.get_organization(membership.organization_id)
            if organization is None or organization.status != "active":
                continue
            organizations.append(
                {
                    "id": organization.id,
                    "code": organization.code,
                    "name": organization.name,
                    "role": membership.role,
                }
            )
        return organizations

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
                    "medical_care_access": membership.medical_care_access,
                    "capabilities": {
                        "can_view_medical_care": membership.status == "active"
                        and (
                            membership.role in {"SHELTER_ADMIN", "PLATFORM_ADMIN"}
                            or (membership.role == "STAFF" and membership.medical_care_access)
                        ),
                        "can_manage_series": membership.status == "active"
                        and membership.role in {"SHELTER_ADMIN", "PLATFORM_ADMIN"},
                    },
                }
                for membership in await self.repository.memberships(user.id)
            ],
        }

    async def bind_line_identity(self, *, id_token: str) -> dict:
        """Preserve the existing LINE binding endpoint independently of LIFF entry exchange."""
        if self.line_verifier is None:
            raise DomainError("line_not_configured", "LINE 身分驗證尚未設定", 503)
        line_user_id = await self.line_verifier.verify(id_token)
        binding = await self.repository.get_line_binding(line_user_id)
        if binding is None:
            raise DomainError("line_binding_required", "請先完成 LINE 身分綁定", 403)
        user = await self.repository.get_user(binding.user_id)
        if user is None or user.status != "active":
            raise DomainError("line_binding_invalid", "LINE 身分綁定無效", 403)
        await self.repository.set_authentication_user_scope(user.id)
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

    async def exchange_line_identity(self, *, id_token: str, shelter_entry_reference: str) -> dict:
        if self.line_verifier is None or self.entry_resolver is None:
            raise DomainError("line_not_configured", "LINE 身分驗證尚未設定", 503)
        try:
            line_user_id = await self.line_verifier.verify(id_token)
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError("invalid_line_id_token", "無法確認 LINE 身分", 401) from exc
        try:
            entry = await self.entry_resolver.resolve(shelter_entry_reference)
        except Exception as exc:
            raise DomainError("liff_exchange_unavailable", "志工入口暫時無法使用", 503) from exc
        if entry is None:
            raise DomainError("entry_unavailable", "此志工入口目前無法使用", 403)
        public_context = {
            "organization": {
                "id": entry.organization_id,
                "code": entry.organization_code,
                "name": entry.organization_name,
            }
        }
        try:
            return await self._exchange_verified_line_identity(
                line_user_id=line_user_id,
                organization_id=entry.organization_id,
                public_context=public_context,
            )
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError("liff_exchange_unavailable", "志工入口暫時無法使用", 503) from exc

    async def _exchange_verified_line_identity(
        self, *, line_user_id: str, organization_id: UUID, public_context: dict
    ) -> dict:
        binding = await self.repository.lock_line_binding(line_user_id)
        if binding is None:
            return {
                "state": "NEW",
                "next_path": "/volunteer-application",
                **public_context,
            }
        await self.repository.set_authentication_context_scope(binding.user_id, organization_id)
        user = await self.repository.lock_user(binding.user_id)
        if user is None or user.status != "active":
            return {"state": "SUSPENDED", **public_context}
        effective_access = await self.repository.lock_effective_volunteer_access(
            user.id, organization_id
        )
        if effective_access is None:
            raw_membership = await self.repository.get_membership(user.id, organization_id)
            if raw_membership is not None and raw_membership.role == "VOLUNTEER":
                return {"state": "SUSPENDED", **public_context}
            application = await self.repository.latest_volunteer_application(
                user.id, organization_id
            )
            if application is not None and application.status == "pending":
                return {"state": "PENDING", **public_context}
            return {
                "state": "NEW",
                "next_path": "/volunteer-application",
                **public_context,
            }
        session = SessionRecord(
            user_id=user.id,
            active_organization_id=organization_id,
            status="active",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.refresh_ttl_seconds),
        )
        await self.repository.add(session)
        issued = await self._issue_session(user.id, session)
        return {
            "state": "ACTIVE",
            **issued,
            "user": {"role": "VOLUNTEER"},
            **public_context,
            "next_path": "/animal-confirmation",
        }

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
