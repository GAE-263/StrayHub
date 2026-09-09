"""Google identity changes; callers own commit/rollback of successful operations."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, select

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.application.authentication.session_service import SessionService
from services.api.app.application.ports.authentication import GoogleIdentityVerifierPort
from services.api.app.persistence.models.identity import (
    GoogleAuthTransaction,
    GoogleUserBinding,
    SessionRecord,
    User,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class GoogleAuthenticationService:
    def __init__(self, sessions: SessionService, verifier: GoogleIdentityVerifierPort):
        self.sessions = sessions
        self.repository = sessions.repository
        self.db = self.repository.session
        self.verifier = verifier

    async def audit(self, user_id: UUID, action: str) -> None:
        await self.repository.set_authentication_user_scope(user_id)
        await AuditService(self.db).record(
            organization_id=None,
            actor_user_id=user_id,
            resource_id=user_id,
            action=action,
            resource_type="account",
            source_channel="web",
        )

    async def reauthenticate(self, user_id: UUID, password: str) -> User:
        user = await self.repository.lock_user(user_id)
        if (
            user is None
            or user.status != "active"
            or not user.password_hash
            or not (self.sessions.password_hasher.verify(password, user.password_hash))
        ):
            raise DomainError("invalid_credentials", "帳號驗證失敗", 401)
        return user

    async def begin(
        self,
        *,
        purpose: str,
        client_id: str,
        display_name: str | None = None,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        password: str = "",
    ) -> tuple[dict, str]:
        if purpose == "link":
            if user_id is None or session_id is None:
                raise DomainError("authentication_required", "請先登入原帳號", 401)
            await self.reauthenticate(user_id, password)
        elif purpose != "login":
            raise DomainError("invalid_transaction", "登入交易無效", 403)
        browser, csrf, nonce = (secrets.token_urlsafe(32) for _ in range(3))
        now = datetime.now(timezone.utc)
        stale = (
            select(GoogleAuthTransaction.id)
            .where(GoogleAuthTransaction.expires_at < now - timedelta(days=1))
            .limit(100)
        )
        await self.db.execute(
            delete(GoogleAuthTransaction).where(GoogleAuthTransaction.id.in_(stale))
        )
        transaction = await self.repository.add(
            GoogleAuthTransaction(
                purpose=purpose,
                client_id=client_id,
                browser_digest=digest(browser),
                csrf_digest=digest(csrf),
                nonce_digest=digest(nonce),
                user_id=user_id,
                session_id=session_id,
                display_name=display_name,
                expires_at=now + timedelta(minutes=5),
                consumed=False,
            )
        )
        return {
            "transaction_id": transaction.id,
            "nonce": nonce,
            "csrf_token": csrf,
            "client_id": client_id,
            "expires_in": 300,
        }, browser

    @staticmethod
    def validate_transaction(transaction, *, browser: str, csrf: str, client_id: str) -> None:
        if (
            transaction is None
            or transaction.consumed
            or transaction.expires_at <= datetime.now(timezone.utc)
            or transaction.client_id != client_id
            or not browser
            or not csrf
            or not secrets.compare_digest(transaction.browser_digest, digest(browser))
            or not secrets.compare_digest(transaction.csrf_digest, digest(csrf))
        ):
            raise DomainError("invalid_transaction", "登入交易已失效，請重新開始", 403)

    async def exchange(
        self,
        *,
        transaction_id: UUID,
        credential: str,
        browser: str,
        csrf: str,
        client_id: str,
        actor_user_id: UUID | None = None,
        actor_session_id: UUID | None = None,
    ) -> dict:
        transaction = await self.repository.google_transaction(transaction_id)
        self.validate_transaction(transaction, browser=browser, csrf=csrf, client_id=client_id)
        claims = await self.verifier.verify(credential, client_id=client_id)
        transaction = await self.repository.google_transaction(transaction_id, lock=True)
        self.validate_transaction(transaction, browser=browser, csrf=csrf, client_id=client_id)
        nonce = claims.get("nonce")
        sub = claims.get("sub")
        if (
            not isinstance(nonce, str)
            or not isinstance(sub, str)
            or not sub
            or not (secrets.compare_digest(transaction.nonce_digest, digest(nonce)))
        ):
            raise DomainError("invalid_google_token", "Google 身分驗證失敗", 401)
        await self.repository.lock_google_subject(digest("google:" + sub))
        binding = await self.repository.google_binding(sub=sub)
        if transaction.purpose == "link":
            if (actor_user_id, actor_session_id) != (transaction.user_id, transaction.session_id):
                raise DomainError("invalid_transaction", "請使用原帳號完成綁定", 403)
            user = await self.repository.lock_user(actor_user_id)
            active_session = await self.repository.lock_session(actor_session_id)
            if (
                active_session is None
                or active_session.status != "active"
                or active_session.user_id != actor_user_id
                or active_session.expires_at <= datetime.now(timezone.utc)
            ):
                raise DomainError("invalid_session", "Session 無效", 401)
            existing = await self.repository.google_binding(user_id=actor_user_id)
            if user is None or user.status != "active":
                raise DomainError("invalid_session", "Session 無效", 401)
            if (binding and binding.user_id != user.id) or (
                existing and existing.google_sub != sub
            ):
                raise DomainError("google_binding_conflict", "無法綁定此 Google 帳號", 409)
            if binding is None:
                await self.repository.add(GoogleUserBinding(google_sub=sub, user_id=user.id))
            else:
                binding.status = "active"
            transaction.consumed = True
            await self.audit(user.id, "google.linked")
            return {"state": "linked"}
        if binding is None:
            if not transaction.display_name:
                raise DomainError(
                    "google_registration_required", "請選擇建立新帳號或登入原帳號綁定", 409
                )
            user = await self.repository.add(
                User(
                    username=None,
                    password_hash=None,
                    display_name=transaction.display_name,
                    platform_role=None,
                    status="active",
                )
            )
            await self.repository.add(GoogleUserBinding(google_sub=sub, user_id=user.id))
            await self.audit(user.id, "google.registered")
        else:
            if binding.status != "active":
                raise DomainError("invalid_google_token", "Google 身分驗證失敗", 401)
            user = await self.repository.lock_user(binding.user_id)
            binding = await self.repository.google_binding(sub=sub)
            if binding is None or binding.status != "active":
                raise DomainError("invalid_google_token", "Google 身分驗證失敗", 401)
            if user is None or user.status != "active":
                raise DomainError("invalid_google_token", "Google 身分驗證失敗", 401)
        transaction.consumed = True
        session = await self.repository.add(
            SessionRecord(
                user_id=user.id,
                status="active",
                session_origin="local_web",
                public_profile=None,
                account_access_enabled=True,
                expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=self.sessions.refresh_ttl_seconds),
            )
        )
        result = await self.sessions._issue_session(user.id, session)
        await self.audit(user.id, "google.logged_in")
        return result

    async def unlink(self, *, user_id: UUID, password: str) -> None:
        user = await self.reauthenticate(user_id, password)
        if user.platform_role != "PLATFORM_ADMIN" and not (
            await self.repository.effective_organization_access(user_id)
        ):
            raise DomainError(
                "last_login_method", "原帳密目前沒有可登入的收容所權限，無法解除 Google", 409
            )
        binding = await self.repository.google_binding(user_id=user_id)
        if binding is None or binding.status != "active":
            raise DomainError("google_binding_missing", "尚未綁定 Google", 409)
        binding.status = "revoked"
        records = (
            await self.db.scalars(
                select(SessionRecord).where(
                    SessionRecord.user_id == user_id, SessionRecord.status == "active"
                )
            )
        ).all()
        for record in records:
            await self.sessions.logout(session_id=record.id)
        await self.audit(user_id, "google.unlinked")

    async def account(self, *, user_id: UUID, session_id: UUID) -> dict:
        user = await self.repository.get_user(user_id)
        record = await self.repository.get_session(session_id)
        access = await self.repository.effective_organization_access(user_id)
        organizations = [
            {"id": org.id, "code": org.code, "name": org.name, "role": member.role}
            for member, org in access
        ]
        if user.platform_role == "PLATFORM_ADMIN":
            # Platform navigation remains in its existing explicitly authorized API.
            organizations = []
        binding = await self.repository.google_binding(user_id=user_id)
        active = next(
            (org for org in organizations if org["id"] == record.active_organization_id), None
        )
        if record.account_access_enabled and not active and user.platform_role != "PLATFORM_ADMIN":
            record.active_organization_id = None
        return {
            "user": {
                "id": user.id,
                "display_name": user.display_name,
                "username": user.username,
                "platform_role": user.platform_role,
            },
            "organizations": organizations,
            "state": "ready" if organizations or user.platform_role else "account_only",
            "login_methods": {
                "password": bool(user.password_hash),
                "google": bool(binding and binding.status == "active"),
            },
        }
