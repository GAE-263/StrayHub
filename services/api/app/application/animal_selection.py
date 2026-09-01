from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_reporting_authorization import (
    VolunteerReportingAuthorizationService,
)
from services.api.app.config.settings import get_settings
from services.api.app.domain.organization_timezone import local_day_range, local_today
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.shelter_area import ShelterArea
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.care_report_repository import CareReportRepository
from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository


class FindAnimalAction(StrEnum):
    QR = "qr"
    SEARCH = "search"
    TODAY = "today"


@dataclass(frozen=True)
class AnimalCandidate:
    animal: Animal
    area: ShelterArea | None

    def confirmation(self, *, organization_name: str) -> AnimalConfirmation:
        return AnimalConfirmation(
            animal_id=self.animal.id,
            name=self.animal.name,
            shelter_number=self.animal.shelter_number,
            area=self.area.name if self.area is not None else None,
            photo_reference=self.animal.current_photo_key,
            organization_id=self.animal.organization_id,
            organization_name=organization_name,
        )


@dataclass(frozen=True)
class AnimalConfirmation:
    animal_id: UUID
    name: str
    shelter_number: str | None
    area: str | None
    photo_reference: str | None
    organization_id: UUID
    organization_name: str


@dataclass(frozen=True)
class CandidatePage:
    items: tuple[AnimalCandidate, ...]
    page: int
    page_size: int
    total: int

    @property
    def has_more(self) -> bool:
        return self.page * self.page_size < self.total


@dataclass(frozen=True)
class TodayAnimalCandidate:
    candidate: AnimalCandidate
    report_count: int
    latest_submitted_at: datetime | None


@dataclass(frozen=True)
class TodayListResult:
    unreported: tuple[TodayAnimalCandidate, ...]
    reported: tuple[TodayAnimalCandidate, ...]
    page: int
    page_size: int
    unreported_total: int
    reported_total: int

    @property
    def unreported_has_more(self) -> bool:
        return self.page * self.page_size < self.unreported_total

    @property
    def reported_has_more(self) -> bool:
        return self.page * self.page_size < self.reported_total


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_animal_confirmation_token(
    *,
    user_id: UUID,
    organization_id: UUID,
    membership_id: UUID,
    session_id: UUID,
    animal_id: UUID,
    ttl_seconds: int = 300,
) -> str:
    payload = {
        "user_id": str(user_id),
        "organization_id": str(organization_id),
        "membership_id": str(membership_id),
        "session_id": str(session_id),
        "animal_id": str(animal_id),
        "expires_at": int(time.time()) + ttl_seconds,
    }
    encoded = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(
        get_settings().animal_confirmation_secret.encode(), encoded.encode(), hashlib.sha256
    ).digest()
    return f"{encoded}.{_encode(signature)}"


def verify_animal_confirmation_token(
    token: str,
    *,
    user_id: UUID,
    organization_id: UUID,
    membership_id: UUID,
    session_id: UUID,
    animal_id: UUID,
) -> None:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(
            get_settings().animal_confirmation_secret.encode(), encoded.encode(), hashlib.sha256
        ).digest()
        payload = json.loads(_decode(encoded))
        valid_signature = hmac.compare_digest(_decode(signature), expected)
        valid_expiry = int(payload["expires_at"]) >= int(time.time())
        expected_values = {
            "user_id": str(user_id),
            "organization_id": str(organization_id),
            "membership_id": str(membership_id),
            "session_id": str(session_id),
            "animal_id": str(animal_id),
        }
        valid_claims = all(payload.get(key) == value for key, value in expected_values.items())
    except (
        binascii.Error,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        valid_signature = False
        valid_expiry = False
        valid_claims = False
    if not (valid_signature and valid_expiry and valid_claims):
        raise DomainError("animal_confirmation_required", "請先確認回報的動物", 409)


class AnimalSelectionService:
    def __init__(
        self,
        animals: AnimalRepository,
        qr_codes: QrCodeRepository,
        authorization: VolunteerReportingAuthorizationService,
    ) -> None:
        self.animals = animals
        self.qr_codes = qr_codes
        self.authorization = authorization

    async def list_candidates(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
        membership_id: UUID | None,
        role: str,
        query: str | None = None,
    ) -> list[AnimalCandidate]:
        if role == "VOLUNTEER":
            await self.authorization.authorize(
                user_id=user_id,
                organization_id=organization_id,
                membership_id=membership_id,
            )
        rows = (
            await self.animals.search_with_area(query)
            if query is not None
            else await self.animals.list_active_with_area()
        )
        return [AnimalCandidate(animal, area) for animal, area in rows]

    async def search_page(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
        membership_id: UUID | None,
        role: str,
        query: str,
        page: int = 1,
        page_size: int = 10,
    ) -> CandidatePage:
        if page < 1 or not 1 <= page_size <= 50:
            raise DomainError("invalid_pagination", "分頁參數無效", 422)
        if role == "VOLUNTEER":
            await self.authorization.authorize(
                user_id=user_id,
                organization_id=organization_id,
                membership_id=membership_id,
            )
        rows, total = await self.animals.search_with_area_page(
            query, offset=(page - 1) * page_size, limit=page_size
        )
        return CandidatePage(
            items=tuple(AnimalCandidate(animal, area) for animal, area in rows),
            page=page,
            page_size=page_size,
            total=total,
        )

    async def resolve_qr(
        self,
        *,
        raw_token: str,
        user_id: UUID,
        organization_id: UUID,
        membership_id: UUID | None,
        role: str,
    ) -> AnimalCandidate:
        qr_code = await self.qr_codes.resolve(raw_token)
        if qr_code is None or qr_code.organization_id != organization_id:
            raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
        if role == "VOLUNTEER":
            await self.authorization.authorize(
                user_id=user_id,
                organization_id=organization_id,
                membership_id=membership_id,
                animal_id=qr_code.animal_id,
            )
        row = await self.animals.get_with_area(qr_code.animal_id)
        if row is None:
            raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
        animal, area = row
        if (
            animal.status != "active"
            or animal.organization_id != organization_id
            or qr_code.animal_id != animal.id
            or qr_code.organization_id != animal.organization_id
        ):
            raise DomainError("animal_not_found", "動物不存在或無法回報", 404)
        return AnimalCandidate(animal, area)

    async def confirm(
        self,
        *,
        animal_id: UUID,
        user_id: UUID,
        organization_id: UUID,
        membership_id: UUID | None,
        role: str,
    ) -> AnimalCandidate:
        if role == "VOLUNTEER":
            await self.authorization.authorize(
                user_id=user_id,
                organization_id=organization_id,
                membership_id=membership_id,
                animal_id=animal_id,
            )
        row = await self.animals.get_with_area(animal_id)
        if row is None:
            raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
        animal, area = row
        if animal.status != "active" or animal.organization_id != organization_id:
            raise DomainError("animal_not_found", "動物不存在或無法回報", 404)
        return AnimalCandidate(animal, area)


class TodayAnimalListService:
    def __init__(
        self,
        animals: AnimalRepository,
        reports: CareReportRepository,
        authorization: VolunteerReportingAuthorizationService,
    ) -> None:
        self.animals = animals
        self.reports = reports
        self.authorization = authorization

    async def list_today(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
        membership_id: UUID | None,
        timezone_name: str,
        page: int = 1,
        page_size: int = 10,
        now: datetime | None = None,
    ) -> TodayListResult:
        if page < 1 or not 1 <= page_size <= 50:
            raise DomainError("invalid_pagination", "分頁參數無效", 422)
        await self.authorization.authorize(
            user_id=user_id,
            organization_id=organization_id,
            membership_id=membership_id,
        )
        day = local_today(timezone_name, now)
        start, end = local_day_range(day, timezone_name)
        rows = await self.animals.list_active_with_area()
        stats = await self.reports.daily_stats_by_animal(start=start, end=end)
        all_items = [
            TodayAnimalCandidate(
                candidate=AnimalCandidate(animal, area),
                report_count=stats.get(animal.id, (0, None))[0],
                latest_submitted_at=stats.get(animal.id, (0, None))[1],
            )
            for animal, area in rows
        ]
        unreported = [item for item in all_items if item.report_count == 0]
        reported = [item for item in all_items if item.report_count > 0]
        offset = (page - 1) * page_size
        return TodayListResult(
            unreported=tuple(unreported[offset : offset + page_size]),
            reported=tuple(reported[offset : offset + page_size]),
            page=page,
            page_size=page_size,
            unreported_total=len(unreported),
            reported_total=len(reported),
        )
