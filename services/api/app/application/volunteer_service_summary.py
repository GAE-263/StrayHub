"""Authorization and aggregation for cross-shelter volunteer experience."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.domain.tenant_context import TenantContext
from services.api.app.domain.volunteer_experience import (
    VolunteerVisitStatistics,
    calculate_visit_statistics,
)
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)
from services.api.app.persistence.repositories.volunteer_service_summary_repository import (
    VolunteerServiceSummaryRepository,
)

SUMMARY_PURPOSE = "volunteer_service_history_review"


@dataclass(frozen=True)
class VolunteerServiceSummaryResult:
    subject_user_id: UUID
    statistics: VolunteerVisitStatistics
    has_active_platform_restriction: bool


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
        as_of: date,
    ) -> VolunteerServiceSummaryResult:
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
        application, _ = detail
        records = await self.summary_repository.list_visit_records(application.user_id)
        restricted = await self.summary_repository.has_active_platform_restriction(
            application.user_id
        )
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
        return VolunteerServiceSummaryResult(
            subject_user_id=application.user_id,
            statistics=calculate_visit_statistics(
                records,
                current_organization_id=self.access_repository.organization_id,
                as_of=as_of,
            ),
            has_active_platform_restriction=restricted,
        )
