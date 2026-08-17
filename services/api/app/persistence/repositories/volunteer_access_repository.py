"""Organization-scoped persistence primitives for volunteer access CRM."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TypeVar
from uuid import UUID

from sqlalchemy import Select, and_, func, select, text, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.domain.volunteer_access import (
    ENTRY_REFERENCE_PURPOSE,
    digest_entry_reference,
)
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.identity import Organization, User
from services.api.app.persistence.models.volunteer_access import (
    OrganizationVolunteerAccessPolicy,
    VolunteerAccessGrant,
    VolunteerApplication,
    VolunteerDecisionBatch,
    VolunteerDecisionBatchItem,
    VolunteerNotificationDelivery,
    VolunteerNotificationRetryBatch,
    VolunteerNotificationRetryBatchItem,
)

T = TypeVar("T")


class VolunteerAccessRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        if not isinstance(organization_id, UUID):
            raise DomainError("organization_scope_required", "缺少收容所資料範圍", 403)
        self.session = session
        self.organization_id = organization_id

    @staticmethod
    async def resolve_entry_reference(
        session: AsyncSession,
        *,
        token_digest: str,
        purpose: str,
    ) -> tuple[UUID, UUID] | None:
        result = await session.execute(
            text(
                """SELECT reference_id, organization_id
                FROM resolve_volunteer_entry_reference(:token_digest, :purpose)"""
            ),
            {"token_digest": token_digest, "purpose": purpose},
        )
        row = result.one_or_none()
        return None if row is None else (row.reference_id, row.organization_id)

    @classmethod
    async def resolve_and_scope(
        cls, session: AsyncSession, raw_reference: str
    ) -> tuple[UUID, UUID] | None:
        resolved = await cls.resolve_entry_reference(
            session,
            token_digest=digest_entry_reference(raw_reference),
            purpose=ENTRY_REFERENCE_PURPOSE,
        )
        if resolved is None:
            return None
        _, organization_id = resolved
        await set_organization_scope(session, organization_id)
        return resolved

    async def add(self, value: T) -> T:
        value_organization_id = getattr(value, "organization_id", None)
        if value_organization_id != self.organization_id:
            raise DomainError("organization_scope_mismatch", "收容所資料範圍不符", 404)
        self.session.add(value)
        await self.session.flush()
        return value

    async def policy(self, *, for_update: bool = False) -> OrganizationVolunteerAccessPolicy:
        statement = select(OrganizationVolunteerAccessPolicy).where(
            OrganizationVolunteerAccessPolicy.organization_id == self.organization_id
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        policy = result.scalar_one_or_none()
        if policy is None:
            raise DomainError("volunteer_access_policy_not_found", "志工入口設定不存在", 404)
        return policy

    def _application_scope(self) -> Select[tuple[VolunteerApplication]]:
        return select(VolunteerApplication).where(
            VolunteerApplication.organization_id == self.organization_id
        )

    async def application(
        self, application_id: UUID, *, for_update: bool = False
    ) -> VolunteerApplication | None:
        statement = self._application_scope().where(VolunteerApplication.id == application_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def pending_application_for_user(
        self, user_id: UUID, *, for_update: bool = False
    ) -> VolunteerApplication | None:
        statement = self._application_scope().where(
            VolunteerApplication.user_id == user_id,
            VolunteerApplication.status == "pending",
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def application_by_client_request(
        self, user_id: UUID, client_request_id: UUID
    ) -> VolunteerApplication | None:
        result = await self.session.execute(
            self._application_scope().where(
                VolunteerApplication.user_id == user_id,
                VolunteerApplication.client_request_id == client_request_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_application_with_race_recovery(
        self, application: VolunteerApplication
    ) -> tuple[VolunteerApplication, bool]:
        try:
            async with self.session.begin_nested():
                self.session.add(application)
                await self.session.flush()
            return application, True
        except IntegrityError:
            existing = await self.pending_application_for_user(application.user_id, for_update=True)
            if existing is None and application.client_request_id is not None:
                existing = await self.application_by_client_request(
                    application.user_id, application.client_request_id
                )
            if existing is None:
                raise
            return existing, False

    async def applications_for_user(
        self, user_id: UUID, *, limit: int = 50
    ) -> list[VolunteerApplication]:
        statement = (
            self._application_scope()
            .where(VolunteerApplication.user_id == user_id)
            .order_by(VolunteerApplication.submitted_at.desc(), VolunteerApplication.id.desc())
            .limit(min(max(limit, 1), 100))
        )
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def list_applications(
        self,
        *,
        status: str | None = None,
        submitted_from: datetime | None = None,
        submitted_to: datetime | None = None,
        cursor: tuple[datetime, UUID] | None = None,
        limit: int = 100,
    ) -> list[VolunteerApplication]:
        statement = self._application_scope()
        if status is not None:
            statement = statement.where(VolunteerApplication.status == status)
        if submitted_from is not None:
            statement = statement.where(VolunteerApplication.submitted_at >= submitted_from)
        if submitted_to is not None:
            statement = statement.where(VolunteerApplication.submitted_at < submitted_to)
        if cursor is not None:
            submitted_at, application_id = cursor
            statement = statement.where(
                tuple_(VolunteerApplication.submitted_at, VolunteerApplication.id)
                < tuple_(submitted_at, application_id)
            )
        statement = statement.order_by(
            VolunteerApplication.submitted_at.desc(), VolunteerApplication.id.desc()
        ).limit(min(max(limit, 1), 500))
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def count_applications(
        self,
        *,
        status: str | None = None,
        submitted_from: datetime | None = None,
        submitted_to: datetime | None = None,
    ) -> int:
        statement = select(func.count(VolunteerApplication.id)).where(
            VolunteerApplication.organization_id == self.organization_id
        )
        if status is not None:
            statement = statement.where(VolunteerApplication.status == status)
        if submitted_from is not None:
            statement = statement.where(VolunteerApplication.submitted_at >= submitted_from)
        if submitted_to is not None:
            statement = statement.where(VolunteerApplication.submitted_at < submitted_to)
        return int((await self.session.execute(statement)).scalar_one())

    async def pending_snapshot(
        self,
        *,
        snapshot_at: datetime,
        status: str = "pending",
        submitted_from: datetime | None = None,
        submitted_to: datetime | None = None,
    ) -> list[VolunteerApplication]:
        if status != "pending":
            raise DomainError("invalid_batch_filter", "全選快照只接受 pending 狀態", 422)
        statement = self._application_scope().where(
            VolunteerApplication.status == "pending",
            VolunteerApplication.submitted_at <= snapshot_at,
        )
        if submitted_from is not None:
            statement = statement.where(VolunteerApplication.submitted_at >= submitted_from)
        if submitted_to is not None:
            statement = statement.where(VolunteerApplication.submitted_at < submitted_to)
        result = await self.session.execute(
            statement.order_by(VolunteerApplication.submitted_at, VolunteerApplication.id)
        )
        return list(result.scalars())

    async def applications_by_ids(
        self, application_ids: Sequence[UUID]
    ) -> list[VolunteerApplication]:
        if len(application_ids) > 500:
            raise DomainError("explicit_selection_too_large", "單次明確選取最多 500 筆", 422)
        result = await self.session.execute(
            self._application_scope().where(VolunteerApplication.id.in_(application_ids))
        )
        return list(result.scalars())

    async def grant(
        self, grant_id: UUID, *, for_update: bool = False
    ) -> VolunteerAccessGrant | None:
        statement = select(VolunteerAccessGrant).where(
            VolunteerAccessGrant.organization_id == self.organization_id,
            VolunteerAccessGrant.id == grant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def active_grant_for_membership(
        self, membership_id: UUID, *, for_update: bool = False
    ) -> VolunteerAccessGrant | None:
        statement = select(VolunteerAccessGrant).where(
            VolunteerAccessGrant.organization_id == self.organization_id,
            VolunteerAccessGrant.membership_id == membership_id,
            VolunteerAccessGrant.status == "active",
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def grant_for_application(self, application_id: UUID) -> VolunteerAccessGrant | None:
        result = await self.session.execute(
            select(VolunteerAccessGrant).where(
                VolunteerAccessGrant.organization_id == self.organization_id,
                VolunteerAccessGrant.application_id == application_id,
            )
        )
        return result.scalar_one_or_none()

    async def grants_for_user(
        self, user_id: UUID, *, limit: int = 50
    ) -> list[VolunteerAccessGrant]:
        result = await self.session.execute(
            select(VolunteerAccessGrant)
            .where(
                VolunteerAccessGrant.organization_id == self.organization_id,
                VolunteerAccessGrant.user_id == user_id,
            )
            .order_by(VolunteerAccessGrant.approved_at.desc(), VolunteerAccessGrant.id.desc())
            .limit(min(max(limit, 1), 100))
        )
        return list(result.scalars())

    async def list_grants(
        self,
        *,
        status: str | None = None,
        cursor: tuple[datetime, UUID] | None = None,
        limit: int = 100,
    ) -> list[VolunteerAccessGrant]:
        statement = select(VolunteerAccessGrant).where(
            VolunteerAccessGrant.organization_id == self.organization_id
        )
        if status is not None:
            if status not in {"active", "expired", "revoked"}:
                raise DomainError("invalid_grant_status", "授權狀態篩選無效", 422)
            statement = statement.where(VolunteerAccessGrant.status == status)
        if cursor is not None:
            approved_at, grant_id = cursor
            statement = statement.where(
                tuple_(VolunteerAccessGrant.approved_at, VolunteerAccessGrant.id)
                < tuple_(approved_at, grant_id)
            )
        result = await self.session.execute(
            statement.order_by(
                VolunteerAccessGrant.approved_at.desc(), VolunteerAccessGrant.id.desc()
            ).limit(min(max(limit, 1), 500))
        )
        return list(result.scalars())

    async def due_or_invalid_grants(
        self, *, now: datetime, limit: int = 500
    ) -> list[VolunteerAccessGrant]:
        result = await self.session.execute(
            select(VolunteerAccessGrant)
            .join(User, User.id == VolunteerAccessGrant.user_id)
            .join(Organization, Organization.id == VolunteerAccessGrant.organization_id)
            .where(
                VolunteerAccessGrant.organization_id == self.organization_id,
                VolunteerAccessGrant.status == "active",
                (
                    (VolunteerAccessGrant.expires_at <= now)
                    | (User.status != "active")
                    | (Organization.status != "active")
                ),
            )
            .order_by(VolunteerAccessGrant.expires_at, VolunteerAccessGrant.id)
            .with_for_update(skip_locked=True)
            .limit(min(max(limit, 1), 500))
        )
        return list(result.scalars())

    async def batch_by_operation(self, operation_id: UUID) -> VolunteerDecisionBatch | None:
        result = await self.session.execute(
            select(VolunteerDecisionBatch).where(
                VolunteerDecisionBatch.organization_id == self.organization_id,
                VolunteerDecisionBatch.operation_id == operation_id,
            )
        )
        return result.scalar_one_or_none()

    async def batch(self, batch_id: UUID) -> VolunteerDecisionBatch | None:
        result = await self.session.execute(
            select(VolunteerDecisionBatch).where(
                VolunteerDecisionBatch.organization_id == self.organization_id,
                VolunteerDecisionBatch.id == batch_id,
            )
        )
        return result.scalar_one_or_none()

    async def pending_batch_items(
        self, batch_id: UUID, *, limit: int = 500
    ) -> list[VolunteerDecisionBatchItem]:
        result = await self.session.execute(
            select(VolunteerDecisionBatchItem)
            .where(
                VolunteerDecisionBatchItem.organization_id == self.organization_id,
                VolunteerDecisionBatchItem.batch_id == batch_id,
                VolunteerDecisionBatchItem.result == "pending",
            )
            .order_by(VolunteerDecisionBatchItem.id)
            .with_for_update(skip_locked=True)
            .limit(min(max(limit, 1), 500))
        )
        return list(result.scalars())

    async def batch_items_after(
        self,
        batch_id: UUID,
        cursor: UUID | None,
        *,
        result: str | None = None,
        limit: int = 100,
    ) -> list[VolunteerDecisionBatchItem]:
        statement = select(VolunteerDecisionBatchItem).where(
            VolunteerDecisionBatchItem.organization_id == self.organization_id,
            VolunteerDecisionBatchItem.batch_id == batch_id,
        )
        if cursor is not None:
            statement = statement.where(VolunteerDecisionBatchItem.id > cursor)
        if result is not None:
            if result not in {"pending", "succeeded", "conflict", "failed"}:
                raise DomainError("invalid_batch_item_result", "逐筆結果篩選無效", 422)
            statement = statement.where(VolunteerDecisionBatchItem.result == result)
        query_result = await self.session.execute(
            statement.order_by(VolunteerDecisionBatchItem.id).limit(min(max(limit, 1), 500))
        )
        return list(query_result.scalars())

    async def notification_by_idempotency_key(
        self, idempotency_key: str
    ) -> VolunteerNotificationDelivery | None:
        result = await self.session.execute(
            select(VolunteerNotificationDelivery).where(
                VolunteerNotificationDelivery.organization_id == self.organization_id,
                VolunteerNotificationDelivery.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    async def notification(
        self, delivery_id: UUID, *, for_update: bool = False
    ) -> VolunteerNotificationDelivery | None:
        statement = select(VolunteerNotificationDelivery).where(
            VolunteerNotificationDelivery.organization_id == self.organization_id,
            VolunteerNotificationDelivery.id == delivery_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def retry_batch_by_operation(
        self, operation_id: UUID
    ) -> VolunteerNotificationRetryBatch | None:
        result = await self.session.execute(
            select(VolunteerNotificationRetryBatch).where(
                VolunteerNotificationRetryBatch.organization_id == self.organization_id,
                VolunteerNotificationRetryBatch.operation_id == operation_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_notifications(
        self,
        *,
        event_type: str | None = None,
        status: str | None = None,
        failed_from: datetime | None = None,
        failed_to: datetime | None = None,
        cursor: tuple[datetime, UUID] | None = None,
        limit: int = 100,
    ) -> list[VolunteerNotificationDelivery]:
        statement = select(VolunteerNotificationDelivery).where(
            VolunteerNotificationDelivery.organization_id == self.organization_id,
            VolunteerNotificationDelivery.status.in_(("retry_wait", "failed")),
        )
        if event_type is not None:
            statement = statement.where(VolunteerNotificationDelivery.event_type == event_type)
        if status is not None:
            if status not in {"retry_wait", "failed"}:
                raise DomainError("invalid_notification_status", "通知狀態篩選無效", 422)
            statement = statement.where(VolunteerNotificationDelivery.status == status)
        if failed_from is not None:
            statement = statement.where(VolunteerNotificationDelivery.last_failed_at >= failed_from)
        if failed_to is not None:
            statement = statement.where(VolunteerNotificationDelivery.last_failed_at < failed_to)
        if cursor is not None:
            failed_at, delivery_id = cursor
            statement = statement.where(
                tuple_(
                    VolunteerNotificationDelivery.last_failed_at,
                    VolunteerNotificationDelivery.id,
                )
                < tuple_(failed_at, delivery_id)
            )
        result = await self.session.execute(
            statement.order_by(
                VolunteerNotificationDelivery.last_failed_at.desc(),
                VolunteerNotificationDelivery.id.desc(),
            ).limit(min(max(limit, 1), 500))
        )
        return list(result.scalars())

    async def retry_items(self, batch_id: UUID) -> list[VolunteerNotificationRetryBatchItem]:
        result = await self.session.execute(
            select(VolunteerNotificationRetryBatchItem)
            .where(
                VolunteerNotificationRetryBatchItem.organization_id == self.organization_id,
                VolunteerNotificationRetryBatchItem.batch_id == batch_id,
            )
            .order_by(VolunteerNotificationRetryBatchItem.id)
        )
        return list(result.scalars())

    async def add_all(self, values: Sequence[object]) -> None:
        for value in values:
            if getattr(value, "organization_id", None) != self.organization_id:
                raise DomainError("organization_scope_mismatch", "收容所資料範圍不符", 404)
        self.session.add_all(values)
        await self.session.flush()

    async def reconcile_batch_counts(self, batch_id: UUID) -> dict[str, int]:
        result = await self.session.execute(
            select(
                func.count(VolunteerDecisionBatchItem.id).label("requested"),
                func.count(VolunteerDecisionBatchItem.id)
                .filter(VolunteerDecisionBatchItem.result == "succeeded")
                .label("succeeded"),
                func.count(VolunteerDecisionBatchItem.id)
                .filter(VolunteerDecisionBatchItem.result == "conflict")
                .label("conflict"),
                func.count(VolunteerDecisionBatchItem.id)
                .filter(VolunteerDecisionBatchItem.result == "failed")
                .label("failed"),
            ).where(
                and_(
                    VolunteerDecisionBatchItem.organization_id == self.organization_id,
                    VolunteerDecisionBatchItem.batch_id == batch_id,
                )
            )
        )
        row = result.one()
        return {
            "requested": row.requested,
            "succeeded": row.succeeded,
            "conflict": row.conflict,
            "failed": row.failed,
        }


__all__ = ["VolunteerAccessRepository"]
