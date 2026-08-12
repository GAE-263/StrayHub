from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.domain.line_care_report_state import CareReportAnswers
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.care_report import CareReportCorrection
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.care_report_repository import CareReportRepository


class ReportCorrectionService:
    def __init__(
        self,
        reports: CareReportRepository,
        animals: AnimalRepository,
        *,
        volunteer_edit_window_seconds: int = 86400,
        answer_validator: Callable[[str, str], None] | None = None,
        audit: AuditService | None = None,
        source_channel: str = "api",
        usage_service=None,
    ) -> None:
        self.reports = reports
        self.animals = animals
        self.volunteer_edit_window_seconds = volunteer_edit_window_seconds
        self.answer_validator = answer_validator
        self.audit = audit
        self.source_channel = source_channel
        self.usage_service = usage_service

    async def correct(
        self,
        report_id: UUID,
        *,
        actor_user_id: UUID,
        actor_role: str,
        observations: dict | None,
        note: str | None,
        animal_id: UUID | None,
        reason: str,
    ):
        report = await self.reports.get(report_id)
        if report is None:
            raise DomainError("report_not_found", "照護回報不存在或無法存取", 404)
        if not reason.strip():
            raise DomainError("correction_reason_required", "修正原因不可為空", 422)
        now = datetime.now(timezone.utc)
        is_owner = report.volunteer_user_id == actor_user_id
        if actor_role == "VOLUNTEER" and (
            not is_owner
            or report.submitted_at + timedelta(seconds=self.volunteer_edit_window_seconds) < now
        ):
            raise DomainError("report_edit_denied", "目前帳號不能修改此回報", 403)
        if actor_role not in {"VOLUNTEER", "STAFF", "SHELTER_ADMIN", "PLATFORM_ADMIN"}:
            raise DomainError("report_edit_denied", "目前帳號不能修改此回報", 403)
        before = {
            "answers": dict(report.answers),
            "note": report.note,
            "animal_id": str(report.animal_id),
        }
        if observations is not None:
            CareReportAnswers(dict(observations))
            if self.answer_validator is not None:
                for field, value in observations.items():
                    if not isinstance(value, str):
                        raise DomainError("invalid_option", "回報選項格式無效", 422)
                    self.answer_validator(field, value)
        target_animal: Animal | None = None
        if animal_id is not None:
            target_animal = await self.animals.get(animal_id)
            if target_animal is None or target_animal.status != "active":
                raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
            report.animal_id = target_animal.id
            report.animal_name_snapshot = target_animal.name
            report.shelter_number_snapshot = target_animal.shelter_number
        if observations is not None:
            report.answers = dict(observations)
        if note is not None:
            report.note = note
        report.status = "amended"
        after = {
            "answers": dict(report.answers),
            "note": report.note,
            "animal_id": str(report.animal_id),
        }
        await self.reports.add_correction(
            CareReportCorrection(
                organization_id=report.organization_id,
                report_id=report.id,
                actor_user_id=actor_user_id,
                original_animal_id=UUID(before["animal_id"]),
                corrected_animal_id=target_animal.id if target_animal else None,
                before_data=before,
                after_data=after,
                reason=reason,
            )
        )
        if self.audit is not None:
            await self.audit.record(
                organization_id=report.organization_id,
                actor_user_id=actor_user_id,
                action="care_report.corrected",
                resource_type="CareReport",
                resource_id=report.id,
                source_channel=self.source_channel,
                before=before,
                after=after,
                reason=reason,
            )
        if self.usage_service is not None and observations is not None:
            try:
                await self.usage_service.index_report(
                    report, answers=observations, snapshots=report.answer_snapshots
                )
            except Exception:
                pass
        return report

    async def archive(self, report_id: UUID, *, actor_user_id: UUID, reason: str):
        report = await self.reports.get(report_id)
        if report is None:
            raise DomainError("report_not_found", "照護回報不存在或無法存取", 404)
        if not reason.strip():
            raise DomainError("archive_reason_required", "封存原因不可為空", 422)
        before = {"status": report.status, "archived_at": report.archived_at}
        report.status = "archived"
        report.archived_at = datetime.now(timezone.utc)
        report.archived_by = actor_user_id
        report.archive_reason = reason
        if self.audit is not None:
            await self.audit.record(
                organization_id=report.organization_id,
                actor_user_id=actor_user_id,
                action="care_report.archived",
                resource_type="CareReport",
                resource_id=report.id,
                source_channel=self.source_channel,
                before=before,
                after={
                    "status": report.status,
                    "archived_at": report.archived_at,
                    "archive_reason": report.archive_reason,
                },
                reason=reason,
            )
        return report
