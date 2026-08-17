from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.identity import LineUserBinding
from services.api.app.persistence.models.volunteer_access import (
    VolunteerDecisionBatch,
    VolunteerDecisionBatchItem,
    VolunteerNotificationDelivery,
)


class WorkerVolunteerAccessRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID, *, worker_id: str) -> None:
        self.session = session
        self.organization_id = organization_id
        self.worker_id = worker_id

    async def batch(self, batch_id: UUID) -> VolunteerDecisionBatch | None:
        await set_organization_scope(self.session, self.organization_id)
        result = await self.session.execute(
            select(VolunteerDecisionBatch).where(
                VolunteerDecisionBatch.organization_id == self.organization_id,
                VolunteerDecisionBatch.id == batch_id,
            )
        )
        return result.scalar_one_or_none()

    async def claim_items(
        self, batch_id: UUID, *, limit: int = 500
    ) -> list[VolunteerDecisionBatchItem]:
        await set_organization_scope(self.session, self.organization_id)
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
        items = list(result.scalars())
        now = datetime.now(timezone.utc)
        claim_token = uuid4()
        for item in items:
            item.claim_token = claim_token
            item.claimed_at = now
            item.claimed_by = self.worker_id
        await self.session.flush()
        return items

    async def recover_stale_claims(self, *, timeout_seconds: int = 300) -> int:
        await set_organization_scope(self.session, self.organization_id)
        threshold = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
        result = await self.session.execute(
            select(VolunteerDecisionBatchItem).where(
                VolunteerDecisionBatchItem.organization_id == self.organization_id,
                VolunteerDecisionBatchItem.result == "pending",
                VolunteerDecisionBatchItem.claimed_at < threshold,
            )
        )
        items = list(result.scalars())
        for item in items:
            item.claim_token = None
            item.claimed_at = None
            item.claimed_by = None
        await self.session.flush()
        return len(items)

    async def claim_notifications(self, *, limit: int = 100) -> list[VolunteerNotificationDelivery]:
        await set_organization_scope(self.session, self.organization_id)
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(VolunteerNotificationDelivery)
            .where(
                VolunteerNotificationDelivery.organization_id == self.organization_id,
                VolunteerNotificationDelivery.status.in_(("pending", "retry_wait")),
                VolunteerNotificationDelivery.available_at <= now,
            )
            .order_by(VolunteerNotificationDelivery.available_at, VolunteerNotificationDelivery.id)
            .with_for_update(skip_locked=True)
            .limit(min(max(limit, 1), 500))
        )
        deliveries = list(result.scalars())
        for delivery in deliveries:
            delivery.status = "sending"
            delivery.claim_token = uuid4()
            delivery.claimed_at = now
            delivery.claimed_by = self.worker_id
            delivery.attempt_count += 1
        await self.session.flush()
        return deliveries

    async def recipient_line_user_id(self, line_binding_id: UUID | None) -> str | None:
        if line_binding_id is None:
            return None
        result = await self.session.execute(
            select(LineUserBinding.line_user_id).where(
                LineUserBinding.id == line_binding_id,
                LineUserBinding.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def complete_notification(
        self,
        delivery: VolunteerNotificationDelivery,
        *,
        sent: bool,
        transient: bool = False,
        error_code: str | None = None,
        max_attempts: int = 5,
    ) -> None:
        now = datetime.now(timezone.utc)
        if delivery.status != "sending" or delivery.claimed_by != self.worker_id:
            return
        if sent:
            delivery.status = "sent"
            delivery.sent_at = now
            delivery.last_error_code = None
        else:
            delivery.last_error_code = error_code or "notification_delivery_failed"
            delivery.last_failed_at = now
            if transient and delivery.attempt_count < max_attempts:
                delivery.status = "retry_wait"
                backoff_seconds = min(3600, 30 * (2 ** (delivery.attempt_count - 1)))
                delivery.available_at = now + timedelta(seconds=backoff_seconds)
            else:
                delivery.status = "failed"
        delivery.claim_token = None
        delivery.claimed_at = None
        delivery.claimed_by = None
        await self.session.flush()

    async def recover_stale_notification_claims(self, *, timeout_seconds: int = 300) -> int:
        await set_organization_scope(self.session, self.organization_id)
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(seconds=timeout_seconds)
        result = await self.session.execute(
            select(VolunteerNotificationDelivery).where(
                VolunteerNotificationDelivery.organization_id == self.organization_id,
                VolunteerNotificationDelivery.status == "sending",
                VolunteerNotificationDelivery.claimed_at < threshold,
            )
        )
        deliveries = list(result.scalars())
        for delivery in deliveries:
            delivery.status = "retry_wait"
            delivery.available_at = now
            delivery.claim_token = None
            delivery.claimed_at = None
            delivery.claimed_by = None
        await self.session.flush()
        return len(deliveries)
