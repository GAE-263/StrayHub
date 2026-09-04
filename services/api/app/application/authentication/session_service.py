from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from services.api.app.api.errors import DomainError
from services.api.app.application.authentication.login_abuse import LoginAbuseKeys
from services.api.app.application.line_rich_menu_routing import RichMenuRoutingService
from services.api.app.application.ports.authentication import (
    AccessTokenPort,
    LineIdentityVerifierPort,
    PasswordHasherPort,
    VolunteerEntryResolverPort,
)
from services.api.app.observability.logging import get_logger
from services.api.app.persistence.models.identity import (
    OrganizationMembership,
    RefreshTokenRecord,
    SessionRecord,
    WebhookSession,
)
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)

logger = get_logger(__name__)

_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=19456,t=2,p=1$WA91Jkye+IIpn+07soNWRg$"
    "C2cae1Wk/9IAl1MSZSdA02XcCY2habmqSjKQJ+5zZ8s"
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
        rich_menu_router: RichMenuRoutingService | None = None,
        refresh_ttl_seconds: int = 604800,
        access_ttl_seconds: int = 900,
        abuse_keys: LoginAbuseKeys | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher
        self.access_token = access_token
        self.line_verifier = line_verifier
        self.entry_resolver = entry_resolver
        self.rich_menu_router = rich_menu_router
        self.refresh_ttl_seconds = refresh_ttl_seconds
        self.access_ttl_seconds = access_ttl_seconds
        self.abuse_keys = abuse_keys
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _rate_limited(retry_after: int) -> DomainError:
        return DomainError(
            "login_rate_limited",
            "登入暫時無法處理，請稍後再試",
            429,
            headers={"Retry-After": str(max(1, retry_after))},
        )

    async def login(self, *, username: str, password: str, client_ip: str | None = None) -> dict:
        now = self.now_provider()
        subject_digest: str | None = None
        account_state = None
        if self.abuse_keys is not None:
            if client_ip is None:
                raise DomainError("login_source_unavailable", "登入暫時無法處理", 503)
            ip_decision = await self.repository.consume_login_ip_attempt(
                self.abuse_keys.ip_digest(client_ip), now=now
            )
            subject_digest = self.abuse_keys.account_digest(username)
            account_state = await self.repository.lock_login_account_state(subject_digest, now=now)
            account_retry_after = self.repository.account_retry_after(account_state, now=now)
            if not ip_decision.allowed or account_retry_after is not None:
                raise self._rate_limited(
                    max(ip_decision.retry_after or 0, account_retry_after or 0, 1)
                )

        user = await self.repository.find_user_by_username(username)
        usable_user = user is not None and user.status == "active" and bool(user.password_hash)
        encoded_hash = (
            user.password_hash if usable_user and user is not None else _DUMMY_PASSWORD_HASH
        )
        password_valid = self.password_hasher.verify(password, encoded_hash or _DUMMY_PASSWORD_HASH)
        if not usable_user or not password_valid or user is None:
            if subject_digest is not None:
                retry_after = await self.repository.record_login_failure(
                    subject_digest, state=account_state, now=now
                )
                if retry_after is not None:
                    raise self._rate_limited(retry_after)
            raise DomainError("invalid_credentials", "帳號或密碼錯誤", 401)
        await self.repository.set_authentication_user_scope(user.id)
        if user.platform_role != "PLATFORM_ADMIN" and not await self._has_active_shelter_access(
            user.id
        ):
            if subject_digest is not None:
                retry_after = await self.repository.record_login_failure(
                    subject_digest, state=account_state, now=now
                )
                if retry_after is not None:
                    raise self._rate_limited(retry_after)
            raise DomainError("invalid_credentials", "帳號或密碼錯誤", 401)
        if subject_digest is not None:
            await self.repository.clear_login_account_state(subject_digest)
        if self.password_hasher.needs_rehash(user.password_hash):
            user.password_hash = self.password_hasher.hash(password)
        session = SessionRecord(
            user_id=user.id,
            status="active",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.refresh_ttl_seconds),
        )
        await self.repository.add(session)
        result = await self._issue_session(user.id, session)
        result["platform_role"] = user.platform_role
        if user.platform_role == "PLATFORM_ADMIN":
            # The role was loaded from the verified server-side identity. Move
            # into platform RLS scope before listing organizations; auth-user
            # discovery scope intentionally cannot see tenantless admin data.
            await self.repository.set_platform_scope()
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
        return bool(await self.repository.effective_organization_access(user_id))

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
        for membership, organization in await self.repository.effective_organization_access(
            user_id
        ):
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
        memberships = await self.repository.memberships(user.id)
        grants = await self.repository.access_grants_for_memberships(
            user.id, [membership.id for membership in memberships]
        )
        grant_by_membership_id = {grant.membership_id: grant for grant in grants}

        def serialize_membership(membership: OrganizationMembership) -> dict:
            grant = grant_by_membership_id.get(membership.id)
            matching_grant = (
                grant
                if grant is not None and grant.organization_id == membership.organization_id
                else None
            )
            return {
                "id": membership.id,
                "organization_id": membership.organization_id,
                "user_id": membership.user_id,
                "role": membership.role,
                "status": membership.status,
                "valid_from": membership.valid_from,
                "expires_at": membership.expires_at,
                "access_grant": (
                    {
                        "membership_id": matching_grant.membership_id,
                        "organization_id": matching_grant.organization_id,
                        "status": matching_grant.status,
                        "valid_from": matching_grant.valid_from,
                        "expires_at": matching_grant.expires_at,
                    }
                    if matching_grant is not None
                    else None
                ),
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

        return {
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "platform_role": user.platform_role,
                "status": user.status,
            },
            "memberships": [serialize_membership(membership) for membership in memberships],
        }

    async def bind_line_identity(
        self, *, id_token: str, organization_id: UUID | None = None
    ) -> dict:
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
        available = await self.repository.effective_organization_access(user.id)
        if not available:
            raise DomainError("shelter_context_required", "沒有可使用的收容所權限", 409)
        if organization_id is None and len(available) > 1:
            return {
                "state": "selection_required",
                "organizations": [
                    {
                        "id": organization.id,
                        "code": organization.code,
                        "name": organization.name,
                        "role": membership.role,
                    }
                    for membership, organization in available
                ],
            }
        selected = next(
            (
                (membership, organization)
                for membership, organization in available
                if organization.id == organization_id
            ),
            available[0] if organization_id is None and len(available) == 1 else None,
        )
        if selected is None:
            raise DomainError("shelter_context_denied", "無法使用指定收容所", 403)
        membership, organization = selected
        if organization is None or organization.status != "active":
            raise DomainError("organization_disabled", "收容所目前停用", 403)
        await self.repository.set_authentication_context_scope(user.id, organization.id)
        session = SessionRecord(
            user_id=user.id,
            active_organization_id=organization.id,
            status="active",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.refresh_ttl_seconds),
        )
        await self.repository.add(session)
        await self.repository.revoke_active_webhook_sessions(user.id)
        await self.repository.add(
            WebhookSession(
                user_id=user.id,
                organization_id=organization.id,
                status="active",
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.refresh_ttl_seconds),
            )
        )
        issued = await self._issue_session(user.id, session)
        issued["organization_id"] = organization.id
        await self._link_role_rich_menu(
            line_user_id,
            membership.role,
            organization_selected=True,
        )
        return issued

    async def _link_role_rich_menu(
        self,
        line_user_id: str,
        role: str | None,
        *,
        organization_selected: bool = False,
    ) -> None:
        """Best-effort：依角色綁定對應 Rich Menu；失敗不影響身分綁定結果。"""
        if self.rich_menu_router is None:
            return
        try:
            await self.rich_menu_router.link_for_user(
                line_user_id=line_user_id,
                role=role,
                organization_selected=organization_selected,
            )
        except Exception:
            # 選單切換為非關鍵操作（LINE API 可能暫時不可用）；綁定已成功即回傳。
            # 但一定要留下紀錄：最常見的原因是 .env 的 richMenuId 在重跑
            # sync_line_role_menus.py --apply 之後過期，靜默吞掉會讓人查錯方向。
            logger.warning(
                "linking rich menu failed; menu unchanged (role=%s)",
                role,
                exc_info=True,
            )
            return

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
        # 志工是走 entry 交換身分，不經過 /v1/line/bind，先前這條路徑不會切選單。
        await self._link_role_rich_menu(line_user_id, "VOLUNTEER")
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
