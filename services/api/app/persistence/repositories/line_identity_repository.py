from __future__ import annotations

from datetime import datetime, timezone
from typing import TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.identity import (
    LineUserBinding,
    LineWebhookEvent,
    WebhookSession,
)

T = TypeVar("T")


class LineIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def binding(self, line_user_id: str) -> LineUserBinding | None:
        result = await self.session.execute(
            select(LineUserBinding).where(
                LineUserBinding.line_user_id == line_user_id,
                LineUserBinding.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def sessions(self, user_id: UUID) -> list[WebhookSession]:
        result = await self.session.execute(
            select(WebhookSession).where(
                WebhookSession.user_id == user_id,
                WebhookSession.status == "active",
                WebhookSession.expires_at > datetime.now(timezone.utc),
            )
        )
        return list(result.scalars())

    async def add(self, value: T) -> T:
        self.session.add(value)
        await self.session.flush()
        return value

    async def event(self, webhook_event_id: str) -> LineWebhookEvent | None:
        result = await self.session.execute(
            select(LineWebhookEvent).where(LineWebhookEvent.webhook_event_id == webhook_event_id)
        )
        return result.scalar_one_or_none()

    async def claim_event(
        self,
        *,
        webhook_event_id: str,
        event_type: str,
        redelivery: bool,
    ) -> tuple[LineWebhookEvent, bool]:
        existing_result = await self.session.execute(
            select(LineWebhookEvent)
            .where(LineWebhookEvent.webhook_event_id == webhook_event_id)
            .with_for_update()
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return existing, False
        value = LineWebhookEvent(
            webhook_event_id=webhook_event_id,
            event_type=event_type,
            processing_status="processing",
            redelivery=redelivery,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(value)
                await self.session.flush()
        except IntegrityError:
            # Another webhook transaction won the unique key race.  The
            # savepoint keeps the surrounding event transaction usable so the
            # caller can return a deterministic duplicate result.
            result = await self.session.execute(
                select(LineWebhookEvent)
                .where(LineWebhookEvent.webhook_event_id == webhook_event_id)
                .with_for_update()
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                raise
            return existing, False
        return value, True

    async def complete_event(
        self,
        event: LineWebhookEvent,
        *,
        status: str = "processed",
        error_code: str | None = None,
    ) -> LineWebhookEvent:
        event.processing_status = status
        event.error_code = error_code
        event.processed_at = datetime.now(timezone.utc)
        await self.session.flush()
        return event
