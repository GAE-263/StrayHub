"""Worker-side handler for 毛孩日記's periodic LINE push reminder — a plain
best-effort push per due inquiry, not the queued/claimed delivery pattern
`VolunteerAccessHandler.deliver_notifications` uses (that pattern exists for
compliance-sensitive volunteer-access transitions; a diary nudge is a
low-stakes, idempotent-enough reminder where a missed push just gets caught
on the next 60-second worker iteration)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.application.line_growth_diary_flex import (
    build_growth_diary_reminder_card,
)
from services.api.app.application.ports.line_messaging import LineMessagingPort
from services.api.app.config.settings import get_worker_settings
from services.api.app.domain.growth_diary_reminder import decide_growth_diary_reminder
from services.api.app.infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from services.api.app.persistence.models.adoption_inquiry import AdoptionInquiry
from services.api.app.persistence.models.identity import LineUserBinding


class GrowthDiaryReminderHandler:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def send_due_reminders(
        self,
        organization_id: UUID,
        *,
        messaging: LineMessagingPort | None = None,
        now: datetime | None = None,
    ) -> int:
        now = now or datetime.now(timezone.utc)
        messenger = messaging or LineMessagingApiAdapter(settings=get_worker_settings())
        inquiries = list(
            (
                await self.session.execute(
                    select(AdoptionInquiry).where(
                        AdoptionInquiry.organization_id == organization_id
                    )
                )
            ).scalars()
        )
        sent = 0
        for inquiry in inquiries:
            decision = decide_growth_diary_reminder(
                adopted_at=inquiry.submitted_at,
                last_prompted_at=inquiry.last_growth_diary_prompted_at,
                now=now,
            )
            if not decision.due:
                continue
            line_user_id = await self._line_user_id_for(inquiry.adopter_user_id)
            if line_user_id is None:
                # No LINE binding to push to — still move the clock forward
                # so this inquiry isn't re-evaluated (and logged as "due")
                # every single worker iteration until one exists.
                inquiry.last_growth_diary_prompted_at = now
                continue
            since_days = (
                now - (inquiry.last_growth_diary_prompted_at or inquiry.submitted_at)
            ).days
            card = build_growth_diary_reminder_card(
                inquiry_id=str(inquiry.id),
                animal_name=inquiry.animal_name_snapshot,
                since_days=since_days,
            )
            try:
                await messenger.push(to_user_id=line_user_id, messages=[card])
                sent += 1
            except Exception:
                # Best-effort — the next 60s worker iteration retries since
                # the clock is only advanced on success.
                continue
            inquiry.last_growth_diary_prompted_at = now
        await self.session.flush()
        return sent

    async def _line_user_id_for(self, user_id: UUID) -> str | None:
        result = await self.session.execute(
            select(LineUserBinding.line_user_id).where(
                LineUserBinding.user_id == user_id, LineUserBinding.status == "active"
            )
        )
        return result.scalar_one_or_none()


__all__ = ["GrowthDiaryReminderHandler"]
