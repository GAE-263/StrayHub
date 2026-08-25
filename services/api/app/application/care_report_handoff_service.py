from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.application.animal_selection import verify_animal_confirmation_token
from services.api.app.application.volunteer_reporting_authorization import (
    VolunteerReportingAuthorizationService,
)
from services.api.app.persistence.models.care_report_handoff import CareReportHandoff

HANDOFF_TTL = timedelta(minutes=15)
HANDOFF_SOURCES = {"liff_scan", "qr_deeplink", "shelter_number"}


class CareReportHandoffService:
    def __init__(
        self,
        repository,
        *,
        authorization: VolunteerReportingAuthorizationService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.authorization = authorization
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    async def create_or_replace_handoff(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
        membership_id: UUID,
        session_id: UUID,
        animal_id: UUID,
        confirmation_token: str,
        source: str,
    ) -> CareReportHandoff:
        if source not in HANDOFF_SOURCES:
            raise DomainError("invalid_handoff_source", "照護回報來源無效", 422)
        verify_animal_confirmation_token(
            confirmation_token,
            user_id=user_id,
            organization_id=organization_id,
            membership_id=membership_id,
            session_id=session_id,
            animal_id=animal_id,
        )
        authorized = await self.authorization.authorize(
            user_id=user_id,
            organization_id=organization_id,
            membership_id=membership_id,
            animal_id=animal_id,
            animal_unavailable_status=409,
        )
        assert authorized.animal is not None
        animal = authorized.animal
        now = self.clock()
        return await self.repository.replace_pending(
            CareReportHandoff(
                organization_id=organization_id,
                user_id=user_id,
                membership_id=membership_id,
                animal_id=animal.id,
                status="pending",
                created_at=now,
                updated_at=now,
                expires_at=now + HANDOFF_TTL,
                source=source,
            ),
            now=now,
        )

    async def consume_pending_handoff(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
    ) -> CareReportHandoff:
        if organization_id != self.repository.organization_id:
            raise DomainError("no_pending_handoff", "請先掃描並確認照護動物", 409)
        handoff = await self.repository.lock_pending_for_user(user_id)
        if handoff is None:
            latest = await self.repository.latest_for_user(user_id)
            code = (
                "handoff_already_consumed"
                if latest is not None and latest.status == "consumed"
                else "no_pending_handoff"
            )
            message = (
                "此照護回報交接已使用"
                if code == "handoff_already_consumed"
                else "請先掃描並確認照護動物"
            )
            raise DomainError(code, message, 409)

        now = self.clock()
        if handoff.expires_at <= now:
            handoff.status = "expired"
            await self.repository.flush()
            raise DomainError("handoff_expired", "動物確認已逾時，請重新掃描確認", 409)

        authorized = await self.authorization.authorize(
            user_id=user_id,
            organization_id=organization_id,
            membership_id=handoff.membership_id,
            animal_id=handoff.animal_id,
            animal_unavailable_status=409,
        )
        assert authorized.animal is not None

        handoff.status = "consumed"
        handoff.consumed_at = now
        await self.repository.flush()
        return handoff
