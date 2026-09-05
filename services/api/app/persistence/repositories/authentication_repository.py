from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import TypeVar
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.application.authentication.login_abuse import (
    ACCOUNT_FAILURE_LIMIT,
    ACCOUNT_LOCK_SECONDS,
    IP_ATTEMPT_LIMIT,
    IP_WINDOW_SECONDS,
    LoginLimitDecision,
)
from services.api.app.persistence.database.scope import (
    set_authentication_user_organization_scope,
    set_authentication_user_scope,
    set_organization_scope,
)
from services.api.app.persistence.database.scope import (
    set_platform_scope as set_database_platform_scope,
)
from services.api.app.persistence.models.identity import (
    LineUserBinding,
    LoginAccountAbuseState,
    LoginIpAttempt,
    Organization,
    OrganizationMembership,
    RefreshTokenRecord,
    SessionRecord,
    User,
    WebhookSession,
)
from services.api.app.persistence.models.volunteer_access import (
    VolunteerAccessGrant,
    VolunteerApplication,
)
from services.api.app.persistence.models.volunteer_management import (
    OrganizationVolunteerNumberCounter,
    VolunteerProfile,
)

T = TypeVar("T")


class AuthenticationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_user_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    @staticmethod
    def _advisory_key(digest: str) -> int:
        return int.from_bytes(bytes.fromhex(digest[:16]), byteorder="big", signed=True)

    async def _lock_login_digest(self, digest: str) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": self._advisory_key(digest)},
        )

    async def consume_login_ip_attempt(
        self,
        source_digest: str,
        *,
        now: datetime,
        window_seconds: int = IP_WINDOW_SECONDS,
        limit: int = IP_ATTEMPT_LIMIT,
    ) -> LoginLimitDecision:
        await self._lock_login_digest(source_digest)
        cutoff = now - timedelta(seconds=window_seconds)
        await self.session.execute(
            delete(LoginIpAttempt).where(
                LoginIpAttempt.source_digest == source_digest,
                LoginIpAttempt.attempted_at <= cutoff,
            )
        )
        attempts = list(
            (
                await self.session.execute(
                    select(LoginIpAttempt.attempted_at)
                    .where(
                        LoginIpAttempt.source_digest == source_digest,
                        LoginIpAttempt.attempted_at > cutoff,
                    )
                    .order_by(LoginIpAttempt.attempted_at, LoginIpAttempt.id)
                    .limit(limit)
                )
            ).scalars()
        )
        if len(attempts) >= limit:
            retry_after = max(
                1,
                math.ceil((attempts[0] + timedelta(seconds=window_seconds) - now).total_seconds()),
            )
            return LoginLimitDecision(False, retry_after)
        self.session.add(LoginIpAttempt(source_digest=source_digest, attempted_at=now))
        await self.session.flush()
        await self._cleanup_expired_ip_attempts(cutoff=cutoff)
        return LoginLimitDecision(True)

    async def _cleanup_expired_ip_attempts(
        self, *, cutoff: datetime, batch_size: int = 100
    ) -> None:
        stale_ids = (
            select(LoginIpAttempt.id)
            .where(LoginIpAttempt.attempted_at <= cutoff)
            .order_by(LoginIpAttempt.attempted_at, LoginIpAttempt.id)
            .limit(batch_size)
        )
        await self.session.execute(delete(LoginIpAttempt).where(LoginIpAttempt.id.in_(stale_ids)))

    async def lock_login_account_state(
        self, subject_digest: str, *, now: datetime
    ) -> LoginAccountAbuseState | None:
        await self._lock_login_digest(subject_digest)
        state = (
            await self.session.execute(
                select(LoginAccountAbuseState)
                .where(LoginAccountAbuseState.subject_digest == subject_digest)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if state is not None and state.locked_until is not None and state.locked_until <= now:
            await self.session.delete(state)
            await self.session.flush()
            return None
        return state

    @staticmethod
    def account_retry_after(state: LoginAccountAbuseState | None, *, now: datetime) -> int | None:
        if state is None or state.locked_until is None or state.locked_until <= now:
            return None
        return max(1, math.ceil((state.locked_until - now).total_seconds()))

    async def record_login_failure(
        self,
        subject_digest: str,
        *,
        state: LoginAccountAbuseState | None,
        now: datetime,
    ) -> int | None:
        if state is None:
            state = LoginAccountAbuseState(
                subject_digest=subject_digest,
                consecutive_failures=1,
                last_failed_at=now,
            )
            self.session.add(state)
        else:
            state.consecutive_failures = min(ACCOUNT_FAILURE_LIMIT, state.consecutive_failures + 1)
            state.last_failed_at = now
        if state.consecutive_failures >= ACCOUNT_FAILURE_LIMIT:
            state.locked_until = now + timedelta(seconds=ACCOUNT_LOCK_SECONDS)
        await self.session.flush()
        return self.account_retry_after(state, now=now)

    async def clear_login_account_state(self, subject_digest: str) -> None:
        await self.session.execute(
            delete(LoginAccountAbuseState).where(
                LoginAccountAbuseState.subject_digest == subject_digest
            )
        )

    async def set_authentication_user_scope(self, user_id: UUID) -> None:
        await set_authentication_user_scope(self.session, user_id)

    async def set_authentication_context_scope(self, user_id: UUID, organization_id: UUID) -> None:
        await set_authentication_user_organization_scope(self.session, user_id, organization_id)

    async def set_platform_scope(self) -> None:
        await set_database_platform_scope(self.session)

    async def set_organization_scope(self, organization_id: UUID) -> None:
        await set_organization_scope(self.session, organization_id)

    async def effective_organization_access(
        self, user_id: UUID
    ) -> list[tuple[OrganizationMembership, Organization]]:
        """Discover own memberships, then verify each grant in exact auth scope.

        Authentication callers supply a verified user. Leaves auth-user scope;
        tenant request callers must restore their original organization scope.
        """
        await self.set_authentication_user_scope(user_id)
        candidates = await self.memberships(user_id)
        access = []
        try:
            for candidate in candidates:
                await self.set_authentication_context_scope(user_id, candidate.organization_id)
                membership = await self.get_effective_membership(user_id, candidate.organization_id)
                organization = await self.get_organization(candidate.organization_id)
                if (
                    membership is not None
                    and organization is not None
                    and organization.status == "active"
                ):
                    access.append((membership, organization))
            return access
        finally:
            await self.set_authentication_user_scope(user_id)

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def lock_user(self, user_id: UUID) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def memberships(
        self, user_id: UUID, *, active_only: bool = False
    ) -> list[OrganizationMembership]:
        statement = select(OrganizationMembership).where(OrganizationMembership.user_id == user_id)
        if active_only:
            statement = statement.where(self._effective_membership_predicate())
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def access_grants_for_memberships(
        self, user_id: UUID, membership_ids: list[UUID]
    ) -> list[VolunteerAccessGrant]:
        if not membership_ids:
            return []
        result = await self.session.execute(
            select(VolunteerAccessGrant).where(
                VolunteerAccessGrant.user_id == user_id,
                VolunteerAccessGrant.membership_id.in_(membership_ids),
            )
        )
        return list(result.scalars())

    async def get_membership(
        self, user_id: UUID, organization_id: UUID
    ) -> OrganizationMembership | None:
        statement = select(OrganizationMembership).where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == organization_id,
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def upsert_volunteer_profile(
        self, user_id: UUID, *, surname: str | None
    ) -> VolunteerProfile:
        profile = await self.session.get(VolunteerProfile, user_id)
        if profile is None:
            profile = VolunteerProfile(user_id=user_id, surname=surname)
            self.session.add(profile)
            await self.session.flush()
        elif surname:
            profile.surname = surname
        return profile

    async def get_volunteer_profile(self, user_id: UUID) -> VolunteerProfile | None:
        return await self.session.get(VolunteerProfile, user_id)

    async def allocate_volunteer_no(self, organization_id: UUID) -> str:
        statement = (
            pg_insert(OrganizationVolunteerNumberCounter)
            .values(organization_id=organization_id, next_value=2)
            .on_conflict_do_update(
                index_elements=[OrganizationVolunteerNumberCounter.organization_id],
                set_={"next_value": OrganizationVolunteerNumberCounter.next_value + 1},
            )
            .returning(OrganizationVolunteerNumberCounter.next_value - 1)
        )
        value = (await self.session.execute(statement)).scalar_one()
        return f"V{value:03d}"

    async def get_effective_membership(
        self, user_id: UUID, organization_id: UUID
    ) -> OrganizationMembership | None:
        result = await self.session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == organization_id,
                self._effective_membership_predicate(),
            )
        )
        return result.scalar_one_or_none()

    async def revoke_active_webhook_sessions(self, user_id: UUID) -> None:
        await self.session.execute(
            update(WebhookSession)
            .where(
                WebhookSession.user_id == user_id,
                WebhookSession.status == "active",
            )
            .values(status="revoked")
        )

    async def get_effective_volunteer_membership(
        self, user_id: UUID, organization_id: UUID
    ) -> OrganizationMembership | None:
        result = await self.session.execute(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == "VOLUNTEER",
                self._effective_membership_predicate(),
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def lock_effective_volunteer_access(
        self, user_id: UUID, organization_id: UUID
    ) -> tuple[OrganizationMembership, VolunteerAccessGrant] | None:
        """Lock the exact Membership and Grant used to authorize a LIFF session."""
        database_now = func.now()
        grant_result = await self.session.execute(
            select(VolunteerAccessGrant)
            .where(
                VolunteerAccessGrant.user_id == user_id,
                VolunteerAccessGrant.organization_id == organization_id,
                VolunteerAccessGrant.status == "active",
                VolunteerAccessGrant.valid_from <= database_now,
                VolunteerAccessGrant.expires_at > database_now,
            )
            .with_for_update()
        )
        grant = grant_result.scalar_one_or_none()
        if grant is None:
            return None
        membership_result = await self.session.execute(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.id == grant.membership_id,
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == "VOLUNTEER",
                OrganizationMembership.status == "active",
                OrganizationMembership.valid_from.is_not(None),
                OrganizationMembership.expires_at.is_not(None),
                OrganizationMembership.valid_from <= database_now,
                OrganizationMembership.expires_at > database_now,
            )
            .with_for_update()
        )
        membership = membership_result.scalar_one_or_none()
        return None if membership is None else (membership, grant)

    async def latest_volunteer_application(
        self, user_id: UUID, organization_id: UUID
    ) -> VolunteerApplication | None:
        result = await self.session.execute(
            select(VolunteerApplication)
            .where(
                VolunteerApplication.user_id == user_id,
                VolunteerApplication.organization_id == organization_id,
            )
            .order_by(
                VolunteerApplication.submitted_at.desc(),
                VolunteerApplication.id.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _effective_membership_predicate():
        database_now = func.now()
        return and_(
            OrganizationMembership.status == "active",
            or_(
                OrganizationMembership.role != "VOLUNTEER",
                and_(
                    OrganizationMembership.valid_from.is_not(None),
                    OrganizationMembership.expires_at.is_not(None),
                    OrganizationMembership.valid_from <= database_now,
                    OrganizationMembership.expires_at > database_now,
                    select(VolunteerAccessGrant.id)
                    .where(
                        VolunteerAccessGrant.membership_id == OrganizationMembership.id,
                        VolunteerAccessGrant.organization_id
                        == OrganizationMembership.organization_id,
                        VolunteerAccessGrant.status == "active",
                        VolunteerAccessGrant.valid_from <= database_now,
                        VolunteerAccessGrant.expires_at > database_now,
                    )
                    .exists(),
                ),
            ),
        )

    async def get_organization(self, organization_id: UUID) -> Organization | None:
        return await self.session.get(Organization, organization_id)

    async def organizations(self, *, active_only: bool = False) -> list[Organization]:
        statement = select(Organization).order_by(Organization.name)
        if active_only:
            statement = statement.where(Organization.status == "active")
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def get_session(self, session_id: UUID) -> SessionRecord | None:
        return await self.session.get(SessionRecord, session_id)

    async def lock_session(self, session_id: UUID) -> SessionRecord | None:
        result = await self.session.execute(
            select(SessionRecord).where(SessionRecord.id == session_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_refresh_token(self, digest: str) -> RefreshTokenRecord | None:
        result = await self.session.execute(
            select(RefreshTokenRecord).where(RefreshTokenRecord.token_digest == digest)
        )
        return result.scalar_one_or_none()

    async def refresh_tokens_for_session(self, session_id: UUID) -> list[RefreshTokenRecord]:
        result = await self.session.execute(
            select(RefreshTokenRecord).where(RefreshTokenRecord.session_id == session_id)
        )
        return list(result.scalars())

    async def get_line_binding(self, line_user_id: str) -> LineUserBinding | None:
        result = await self.session.execute(
            select(LineUserBinding).where(
                LineUserBinding.line_user_id == line_user_id,
                LineUserBinding.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def lock_line_binding(self, line_user_id: str) -> LineUserBinding | None:
        result = await self.session.execute(
            select(LineUserBinding)
            .where(
                LineUserBinding.line_user_id == line_user_id,
                LineUserBinding.status == "active",
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_line_binding_for_user(self, user_id: UUID) -> LineUserBinding | None:
        result = await self.session.execute(
            select(LineUserBinding).where(
                LineUserBinding.user_id == user_id,
                LineUserBinding.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def clear_volunteer_contexts(self, user_id: UUID, organization_id: UUID) -> None:
        await self.session.execute(
            update(SessionRecord)
            .where(
                SessionRecord.user_id == user_id,
                SessionRecord.active_organization_id == organization_id,
            )
            .values(active_organization_id=None)
        )
        await self.session.execute(
            update(WebhookSession)
            .where(
                WebhookSession.user_id == user_id,
                WebhookSession.organization_id == organization_id,
                WebhookSession.status == "active",
            )
            .values(status="expired", expires_at=func.now())
        )

    async def get_or_create_line_applicant(
        self, line_user_id: str
    ) -> tuple[User, LineUserBinding, bool]:
        binding = await self.get_line_binding(line_user_id)
        if binding is not None:
            user = await self.get_user(binding.user_id)
            if user is None:
                raise RuntimeError("LINE binding references a missing user") from None
            return user, binding, False
        user = User(display_name="LINE 志工", status="active")
        binding = LineUserBinding(
            line_user_id=line_user_id,
            user_id=user.id,
            status="active",
        )
        try:
            async with self.session.begin_nested():
                self.session.add(user)
                await self.session.flush()
                binding.user_id = user.id
                self.session.add(binding)
                await self.session.flush()
            return user, binding, True
        except IntegrityError:
            binding = await self.get_line_binding(line_user_id)
            if binding is None:
                raise
            user = await self.get_user(binding.user_id)
            if user is None:
                raise RuntimeError("LINE binding references a missing user") from None
            return user, binding, False

    async def revoke_refresh_family(self, family_id: UUID) -> None:
        result = await self.session.execute(
            select(RefreshTokenRecord).where(RefreshTokenRecord.family_id == family_id)
        )
        for record in result.scalars():
            record.status = "revoked"

    async def revoke_remote_management_sessions(self) -> tuple[int, int]:
        sessions = list(
            (
                await self.session.execute(
                    select(SessionRecord)
                    .where(SessionRecord.session_origin == "remote_management_demo")
                    .order_by(SessionRecord.id)
                    .with_for_update()
                )
            ).scalars()
        )
        session_ids = [record.id for record in sessions]
        refresh_tokens = (
            list(
                (
                    await self.session.execute(
                        select(RefreshTokenRecord)
                        .where(RefreshTokenRecord.session_id.in_(session_ids))
                        .order_by(RefreshTokenRecord.id)
                        .with_for_update()
                    )
                ).scalars()
            )
            if session_ids
            else []
        )
        active_sessions = [record for record in sessions if record.status == "active"]
        active_refresh_tokens = [record for record in refresh_tokens if record.status == "active"]
        for record in active_sessions:
            record.status = "revoked"
        for record in active_refresh_tokens:
            record.status = "revoked"
        await self.session.flush()
        return len(active_sessions), len(active_refresh_tokens)

    async def add(self, value: T) -> T:
        self.session.add(value)
        await self.session.flush()
        return value
