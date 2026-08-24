"""Authorization and opaque cursor handling for volunteer service history."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.domain.tenant_context import TenantContext
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)
from services.api.app.persistence.repositories.volunteer_service_summary_repository import (
    VolunteerServiceSummaryRecord,
    VolunteerServiceSummaryRepository,
)

SUMMARY_PURPOSE = "volunteer_service_history_review"


@dataclass(frozen=True)
class VolunteerServiceSummaryPage:
    subject_user_id: UUID
    items: list[VolunteerServiceSummaryRecord]
    has_more: bool


def _digest(value: UUID) -> str:
    return hashlib.sha256(value.bytes).hexdigest()


def encode_summary_cursor(
    secret: str,
    *,
    application_id: UUID,
    subject_user_id: UUID,
    service_date: date,
    organization_id: UUID,
) -> str:
    payload = {
        "application": _digest(application_id),
        "subject": _digest(subject_user_id),
        "service_date": service_date.isoformat(),
        "organization_id": str(organization_id),
        "version": 1,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).decode().rstrip("=")
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
    signature_encoded = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{encoded}.{signature_encoded}"


def decode_summary_cursor(
    secret: str,
    cursor: str,
    *,
    application_id: UUID,
    subject_user_id: UUID,
) -> tuple[date, UUID]:
    try:
        encoded, signature_encoded = cursor.split(".", 1)
        expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
        actual = base64.urlsafe_b64decode(signature_encoded + "=" * (-len(signature_encoded) % 4))
        if not hmac.compare_digest(expected, actual):
            raise ValueError
        payload = json.loads(
            base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
        )
        if (
            payload.get("version") != 1
            or payload.get("application") != _digest(application_id)
            or payload.get("subject") != _digest(subject_user_id)
        ):
            raise ValueError
        return date.fromisoformat(payload["service_date"]), UUID(payload["organization_id"])
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise DomainError("invalid_cursor", "查詢游標無效", 422) from exc


class VolunteerServiceSummaryService:
    def __init__(
        self,
        access_repository: VolunteerAccessRepository,
        summary_repository: VolunteerServiceSummaryRepository,
        *,
        audit: AuditService,
    ) -> None:
        self.access_repository = access_repository
        self.summary_repository = summary_repository
        self.audit = audit

    async def for_application(
        self,
        application_id: UUID,
        *,
        tenant_context: TenantContext,
        purpose_code: str,
        cursor: str | None,
        cursor_secret: str,
        limit: int,
    ) -> VolunteerServiceSummaryPage:
        if purpose_code != SUMMARY_PURPOSE:
            raise DomainError("invalid_purpose", "服務紀錄用途無效", 422)
        if (
            tenant_context.platform_scope
            or tenant_context.role != "SHELTER_ADMIN"
            or tenant_context.organization_id != self.access_repository.organization_id
        ):
            raise DomainError("volunteer_service_summary_denied", "無法讀取志工服務紀錄", 403)
        if await self.access_repository.active_membership(tenant_context.user_id) is None:
            raise DomainError("volunteer_service_summary_denied", "無法讀取志工服務紀錄", 403)

        detail = await self.access_repository.application_detail(application_id)
        if detail is None:
            raise DomainError("volunteer_application_not_found", "志工申請不存在", 404)
        application, _service_dates = detail
        subject_user_id = application.user_id
        decoded_cursor = (
            decode_summary_cursor(
                cursor_secret,
                cursor,
                application_id=application_id,
                subject_user_id=subject_user_id,
            )
            if cursor
            else None
        )
        records = await self.summary_repository.list_for_subject(
            subject_user_id,
            cursor=decoded_cursor,
            limit=limit + 1,
        )
        has_more = len(records) > limit
        page_records = records[:limit]
        try:
            await self.audit.record(
                organization_id=self.access_repository.organization_id,
                actor_user_id=tenant_context.user_id,
                action="volunteer.service_summary.read",
                resource_type="volunteer_application_service_summary",
                resource_id=application_id,
                source_channel="api",
                reason=purpose_code,
            )
        except SQLAlchemyError as exc:
            raise DomainError(
                "service_summary_audit_unavailable", "服務紀錄暫時無法使用", 503
            ) from exc
        return VolunteerServiceSummaryPage(subject_user_id, page_records, has_more)
