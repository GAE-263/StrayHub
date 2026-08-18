from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.audit import AuditRecord
from services.api.app.persistence.models.identity import (
    OrganizationMembership,
    SessionRecord,
    User,
)
from services.api.app.persistence.models.platform_governance import PlatformAdminPolicy
from services.api.app.persistence.models.volunteer_access import VolunteerApplication


class PlatformAdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_policy(self) -> PlatformAdminPolicy:
        result = await self.session.execute(
            select(PlatformAdminPolicy)
            .where(PlatformAdminPolicy.policy_key == "default")
            .with_for_update()
        )
        policy = result.scalar_one_or_none()
        if policy is None:
            raise RuntimeError("platform admin policy is not initialized")
        return policy

    async def policy(self) -> PlatformAdminPolicy:
        result = await self.session.execute(
            select(PlatformAdminPolicy).where(PlatformAdminPolicy.policy_key == "default")
        )
        policy = result.scalar_one_or_none()
        if policy is None:
            raise RuntimeError("platform admin policy is not initialized")
        return policy

    async def active_count(self) -> int:
        result = await self.session.execute(
            select(func.count(User.id)).where(
                User.status == "active", User.platform_role == "PLATFORM_ADMIN"
            )
        )
        return int(result.scalar_one())

    async def user_count(self) -> int:
        result = await self.session.execute(select(func.count(User.id)))
        return int(result.scalar_one())

    async def list_admins(self) -> list[User]:
        result = await self.session.execute(
            select(User)
            .where(User.platform_role == "PLATFORM_ADMIN")
            .order_by(
                (User.status == "active").desc(),
                User.display_name,
                User.username,
            )
        )
        return list(result.scalars())

    async def list_candidates(self) -> list[User]:
        volunteer_membership = (
            select(OrganizationMembership.id)
            .where(
                OrganizationMembership.user_id == User.id,
                OrganizationMembership.role == "VOLUNTEER",
            )
            .exists()
        )
        volunteer_application = (
            select(VolunteerApplication.id)
            .where(
                VolunteerApplication.user_id == User.id,
            )
            .exists()
        )
        result = await self.session.execute(
            select(User)
            .where(
                User.status == "active",
                User.platform_role.is_(None),
                User.username.is_not(None),
                func.trim(User.username) != "",
                ~or_(volunteer_membership, volunteer_application),
            )
            .order_by(User.display_name, User.username)
        )
        return list(result.scalars())

    async def is_volunteer_account(self, user_id: UUID) -> bool:
        result = await self.session.execute(
            select(OrganizationMembership.id)
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.role == "VOLUNTEER",
            )
            .limit(1)
        )
        if result.scalar_one_or_none() is not None:
            return True
        result = await self.session.execute(
            select(VolunteerApplication.id).where(VolunteerApplication.user_id == user_id).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def user(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def user_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def add_user(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def invalidate_sessions(self, user_id: UUID) -> None:
        await self.session.execute(
            SessionRecord.__table__.update()
            .where(SessionRecord.user_id == user_id, SessionRecord.status == "active")
            .values(status="expired", expires_at=datetime.now(timezone.utc))
        )

    async def audit_records(
        self,
        *,
        user_id: UUID | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        statement = select(AuditRecord).where(
            AuditRecord.organization_id.is_(None),
            AuditRecord.resource_type == "platform",
        )
        if user_id is not None:
            statement = statement.where(
                or_(
                    AuditRecord.resource_id == user_id,
                    AuditRecord.actor_user_id == user_id,
                )
            )
        if action:
            statement = statement.where(AuditRecord.action == action)
        result = await self.session.execute(
            statement.order_by(AuditRecord.created_at.desc()).limit(max(1, min(limit, 200)))
        )
        return list(result.scalars())
