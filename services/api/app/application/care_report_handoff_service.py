from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.application.animal_selection import verify_animal_confirmation_token
from services.api.app.persistence.models.care_report_handoff import CareReportHandoff

HANDOFF_TTL = timedelta(minutes=15)
HANDOFF_SOURCES = {"liff_scan", "qr_deeplink", "shelter_number"}


class CareReportHandoffService:
    def __init__(
        self,
        repository,
        *,
        authentication,
        animals,
        reportable_scopes,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.authentication = authentication
        self.animals = animals
        self.reportable_scopes = reportable_scopes
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
        await self._require_effective_access(
            user_id=user_id,
            organization_id=organization_id,
            membership_id=membership_id,
        )
        animal = await self._require_animal(animal_id, organization_id)
        if not await self.reportable_scopes.is_animal_reportable(
            animal_id=animal.id,
            volunteer_user_id=user_id,
        ):
            raise DomainError(
                "authorization_no_longer_valid",
                "目前無法開始此照護回報",
                403,
            )
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

        await self._require_effective_access(
            user_id=user_id,
            organization_id=organization_id,
            membership_id=handoff.membership_id,
        )
        animal = await self._require_animal(handoff.animal_id, organization_id)
        if not await self.reportable_scopes.is_animal_reportable(
            animal_id=animal.id,
            volunteer_user_id=user_id,
        ):
            raise DomainError(
                "authorization_no_longer_valid",
                "目前無法開始此照護回報",
                403,
            )

        handoff.status = "consumed"
        handoff.consumed_at = now
        await self.repository.flush()
        return handoff

    async def _require_effective_access(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
        membership_id: UUID,
    ) -> None:
        user = await self.authentication.get_user(user_id)
        organization = await self.authentication.get_organization(organization_id)
        if (
            user is None
            or user.status != "active"
            or organization is None
            or organization.status != "active"
        ):
            raise DomainError(
                "authorization_no_longer_valid",
                "目前無法開始此照護回報",
                403,
            )
        access = await self.authentication.lock_effective_volunteer_access(user_id, organization_id)
        if access is None:
            raise DomainError(
                "authorization_no_longer_valid",
                "目前無法開始此照護回報",
                403,
            )
        membership, grant = access
        if (
            membership.id != membership_id
            or membership.user_id != user_id
            or membership.organization_id != organization_id
            or membership.role != "VOLUNTEER"
            or grant.user_id != user_id
            or grant.organization_id != organization_id
            or grant.membership_id != membership.id
        ):
            raise DomainError(
                "authorization_no_longer_valid",
                "目前無法開始此照護回報",
                403,
            )

    async def _require_animal(self, animal_id: UUID, organization_id: UUID):
        animal = await self.animals.get(animal_id)
        if animal is None or animal.organization_id != organization_id or animal.status != "active":
            raise DomainError(
                "animal_no_longer_available",
                "動物目前無法進行照護回報",
                409,
            )
        return animal
