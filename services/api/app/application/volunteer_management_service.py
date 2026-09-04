from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.domain.tenant_context import TenantContext
from services.api.app.domain.volunteer_experience import (
    VolunteerVisitStatistics,
    calculate_visit_statistics,
)
from services.api.app.persistence.models.identity import OrganizationMembership
from services.api.app.persistence.models.volunteer_management import (
    VolunteerIncident,
    VolunteerNote,
    VolunteerRestriction,
)
from services.api.app.persistence.repositories.volunteer_management_repository import (
    VolunteerManagementRepository,
)
from services.api.app.persistence.repositories.volunteer_service_summary_repository import (
    VolunteerServiceSummaryRepository,
)


@dataclass(frozen=True)
class VolunteerProfileResult:
    membership: OrganizationMembership
    surname: str | None
    statistics: VolunteerVisitStatistics
    notes: list[tuple[VolunteerNote, str]]
    incidents: list[VolunteerIncident]
    restrictions: list[VolunteerRestriction]


class VolunteerManagementService:
    def __init__(
        self,
        repository: VolunteerManagementRepository,
        summary_repository: VolunteerServiceSummaryRepository,
        audit: AuditService,
    ) -> None:
        self.repository = repository
        self.summary_repository = summary_repository
        self.audit = audit

    def _require_shelter_admin(self, context: TenantContext) -> None:
        if (
            context.platform_scope
            or context.role != "SHELTER_ADMIN"
            or context.organization_id != self.repository.organization_id
        ):
            raise DomainError("volunteer_management_denied", "無法存取志工管理資料", 403)

    async def detail(
        self, membership_id: UUID, *, context: TenantContext, as_of: date
    ) -> VolunteerProfileResult:
        self._require_shelter_admin(context)
        membership = await self.repository.volunteer_membership(membership_id)
        if membership is None:
            raise DomainError("volunteer_not_found", "志工不存在", 404)
        profile = await self.repository.profile(membership.user_id)
        records = await self.summary_repository.list_visit_records(membership.user_id)
        return VolunteerProfileResult(
            membership=membership,
            surname=None if profile is None else profile.surname,
            statistics=calculate_visit_statistics(
                records,
                current_organization_id=self.repository.organization_id,
                as_of=as_of,
            ),
            notes=await self.repository.notes(membership.id),
            incidents=await self.repository.incidents(membership.id),
            restrictions=await self.repository.restrictions(membership),
        )

    async def add_note(
        self,
        membership_id: UUID,
        *,
        content: str,
        context: TenantContext,
        author_membership_id: UUID | None,
    ) -> VolunteerNote:
        self._require_shelter_admin(context)
        if author_membership_id is None:
            raise DomainError("shelter_membership_required", "缺少本所管理身份", 403)
        membership = await self.repository.volunteer_membership(membership_id)
        if membership is None:
            raise DomainError("volunteer_not_found", "志工不存在", 404)
        normalized = content.strip()
        if not normalized or len(normalized) > 2000:
            raise DomainError("invalid_volunteer_note", "備註需為 1 至 2000 字", 422)
        note = await self.repository.add_note(
            VolunteerNote(
                organization_id=self.repository.organization_id,
                subject_membership_id=membership.id,
                author_membership_id=author_membership_id,
                content=normalized,
            )
        )
        await self.audit.record(
            organization_id=self.repository.organization_id,
            actor_user_id=context.user_id,
            action="volunteer.note.created",
            resource_type="volunteer_note",
            resource_id=note.id,
            source_channel="api",
        )
        return note

    async def set_assist_flag(
        self, membership_id: UUID, *, value: bool, context: TenantContext
    ) -> OrganizationMembership:
        self._require_shelter_admin(context)
        membership = await self.repository.volunteer_membership(membership_id, for_update=True)
        if membership is None:
            raise DomainError("volunteer_not_found", "志工不存在", 404)
        before = membership.can_assist_new_volunteers
        membership.can_assist_new_volunteers = value
        await self.audit.record(
            organization_id=self.repository.organization_id,
            actor_user_id=context.user_id,
            action="volunteer.assist_flag.updated",
            resource_type="organization_membership",
            resource_id=membership.id,
            source_channel="api",
            before={"can_assist_new_volunteers": before},
            after={"can_assist_new_volunteers": value},
        )
        return membership

    async def add_incident(
        self,
        membership_id: UUID,
        *,
        incident_type: str,
        severity: str,
        factual_summary: str,
        occurred_at: datetime,
        context: TenantContext,
        author_membership_id: UUID | None,
    ) -> VolunteerIncident:
        self._require_shelter_admin(context)
        if author_membership_id is None:
            raise DomainError("shelter_membership_required", "缺少本所管理身份", 403)
        membership = await self.repository.volunteer_membership(membership_id)
        if membership is None:
            raise DomainError("volunteer_not_found", "志工不存在", 404)
        kind, summary = incident_type.strip(), factual_summary.strip()
        if severity not in {"low", "medium", "high", "critical"}:
            raise DomainError("invalid_incident_severity", "事件嚴重程度無效", 422)
        if not kind or len(kind) > 80 or not summary or len(summary) > 2000:
            raise DomainError("invalid_incident", "事件內容格式無效", 422)
        incident = await self.repository.add_incident(
            VolunteerIncident(
                organization_id=self.repository.organization_id,
                subject_membership_id=membership.id,
                volunteer_user_id=membership.user_id,
                incident_type=kind,
                severity=severity,
                factual_summary=summary,
                occurred_at=occurred_at,
                created_by_membership_id=author_membership_id,
                status="reported",
            )
        )
        await self.audit.record(
            organization_id=self.repository.organization_id,
            actor_user_id=context.user_id,
            action="volunteer.incident.created",
            resource_type="volunteer_incident",
            resource_id=incident.id,
            source_channel="api",
        )
        return incident

    async def request_restriction(
        self,
        incident_id: UUID,
        *,
        scope: str,
        reason_category: str,
        starts_at: datetime,
        ends_at: datetime | None,
        context: TenantContext,
        requester_membership_id: UUID | None,
    ) -> VolunteerRestriction:
        self._require_shelter_admin(context)
        if requester_membership_id is None:
            raise DomainError("shelter_membership_required", "缺少本所管理身份", 403)
        incident = await self.repository.incident(incident_id)
        if incident is None:
            raise DomainError("volunteer_incident_not_found", "志工事件不存在", 404)
        if incident.status != "confirmed":
            raise DomainError("incident_not_confirmed", "事件需經本所管理員確認後才能建立限制", 409)
        if scope not in {"SHELTER", "PLATFORM"}:
            raise DomainError("invalid_restriction_scope", "限制範圍無效", 422)
        if not reason_category.strip() or len(reason_category.strip()) > 80:
            raise DomainError("invalid_restriction_reason", "限制原因類別無效", 422)
        if ends_at is not None and ends_at <= starts_at:
            raise DomainError("invalid_restriction_period", "限制期間無效", 422)
        now = datetime.now(timezone.utc)
        restriction = await self.repository.add_restriction(
            VolunteerRestriction(
                organization_id=self.repository.organization_id,
                volunteer_user_id=incident.volunteer_user_id,
                incident_id=incident.id,
                scope=scope,
                reason_category=reason_category.strip(),
                status="active" if scope == "SHELTER" else "pending_review",
                starts_at=starts_at,
                ends_at=ends_at,
                requested_by_membership_id=requester_membership_id,
                approved_by_user_id=context.user_id if scope == "SHELTER" else None,
                reviewed_at=now if scope == "SHELTER" else None,
            )
        )
        await self.audit.record(
            organization_id=self.repository.organization_id,
            actor_user_id=context.user_id,
            action="volunteer.restriction.created",
            resource_type="volunteer_restriction",
            resource_id=restriction.id,
            source_channel="api",
            after={"scope": scope, "status": restriction.status},
        )
        return restriction

    async def review_incident(
        self,
        incident_id: UUID,
        *,
        decision: str,
        context: TenantContext,
    ) -> VolunteerIncident:
        self._require_shelter_admin(context)
        incident = await self.repository.incident(incident_id, for_update=True)
        if incident is None:
            raise DomainError("volunteer_incident_not_found", "志工事件不存在", 404)
        if incident.status not in {"reported", "under_review"}:
            raise DomainError("incident_already_reviewed", "此事件已完成審查", 409)
        if decision not in {"confirm", "dismiss"}:
            raise DomainError("invalid_incident_decision", "事件審查決定無效", 422)
        incident.status = "confirmed" if decision == "confirm" else "dismissed"
        incident.reviewed_by_user_id = context.user_id
        incident.reviewed_at = datetime.now(timezone.utc)
        await self.audit.record(
            organization_id=self.repository.organization_id,
            actor_user_id=context.user_id,
            action=f"volunteer.incident.{incident.status}",
            resource_type="volunteer_incident",
            resource_id=incident.id,
            source_channel="api",
        )
        return incident

    async def decide_platform_restriction(
        self,
        restriction_id: UUID,
        *,
        decision: str,
        reason: str | None,
        context: TenantContext,
    ) -> VolunteerRestriction:
        if not context.platform_scope or context.role != "PLATFORM_ADMIN":
            raise DomainError("platform_admin_required", "需要平台管理員權限", 403)
        restriction = await self.repository.platform_restriction_for_update(restriction_id)
        if restriction is None:
            raise DomainError("volunteer_restriction_not_found", "志工限制不存在", 404)
        if restriction.status != "pending_review":
            raise DomainError("restriction_already_reviewed", "此限制已完成審查", 409)
        if decision not in {"approve", "reject"}:
            raise DomainError("invalid_restriction_decision", "限制審查決定無效", 422)
        restriction.status = "active" if decision == "approve" else "rejected"
        restriction.approved_by_user_id = context.user_id if decision == "approve" else None
        restriction.reviewed_at = datetime.now(timezone.utc)
        restriction.decision_reason = (reason or "").strip() or None
        await self.audit.record(
            organization_id=restriction.organization_id,
            actor_user_id=context.user_id,
            action=f"volunteer.platform_restriction.{restriction.status}",
            resource_type="volunteer_restriction",
            resource_id=restriction.id,
            source_channel="api",
            reason=restriction.decision_reason,
        )
        return restriction

    async def list_pending_platform_restrictions(
        self, *, context: TenantContext
    ) -> list[tuple[VolunteerRestriction, VolunteerIncident, str]]:
        if not context.platform_scope or context.role != "PLATFORM_ADMIN":
            raise DomainError("platform_admin_required", "需要平台管理員權限", 403)
        rows = await self.repository.pending_platform_restrictions()
        for restriction, _incident, _organization_name in rows:
            await self.audit.record(
                organization_id=restriction.organization_id,
                actor_user_id=context.user_id,
                action="volunteer.platform_restriction.read",
                resource_type="volunteer_restriction",
                resource_id=restriction.id,
                source_channel="api",
            )
        return rows
