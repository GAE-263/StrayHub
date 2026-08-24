from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.domain.line_care_report_state import UNOBSERVED, CareReportAnswers
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.care_report import CareReport
from services.api.app.persistence.repositories.care_report_draft_repository import (
    CareReportDraftRepository,
)
from services.api.app.persistence.repositories.care_report_repository import CareReportRepository


class ReportSubmissionService:
    def __init__(
        self,
        drafts: CareReportDraftRepository,
        reports: CareReportRepository,
        *,
        answer_validator: Callable[[str, str], None] | None = None,
        scope_validator: Callable[[UUID], Awaitable[bool]] | None = None,
        audit=None,
        note_validator: Callable[[dict[str, str], str | None], None] | None = None,
        answer_snapshots: dict[str, dict[str, str]] | None = None,
        usage_service=None,
    ) -> None:
        self.drafts = drafts
        self.reports = reports
        self.answer_validator = answer_validator
        self.scope_validator = scope_validator
        self.audit = audit
        self.note_validator = note_validator
        self.answer_snapshots = answer_snapshots
        self.usage_service = usage_service

    async def submit(
        self,
        *,
        draft_id: UUID,
        volunteer_user_id: UUID,
        animal: Animal,
        idempotency_key: str,
        note: str | None = None,
        story: str | None = None,
        media_asset_ids: list[UUID] | None = None,
    ) -> CareReport:
        existing = await self.reports.get_idempotent(
            volunteer_user_id=volunteer_user_id, key=idempotency_key
        )
        if existing is not None:
            return existing
        draft = await self.drafts.get(draft_id)
        if draft is None:
            raise DomainError("draft_not_found", "草稿不存在或無法存取", 404)
        if draft.status == "submitted":
            existing_report = await self.reports.get_by_draft(draft.id)
            if existing_report is not None:
                return existing_report
        if draft.status != "active":
            raise DomainError("draft_not_found", "草稿不存在或無法存取", 404)
        if draft.current_step not in {"reviewing", "submitting"}:
            raise DomainError("invalid_draft_step", "完成摘要確認後才能送出回報", 409)
        if (
            draft.organization_id != self.reports.organization_id
            or animal.organization_id != draft.organization_id
        ):
            raise DomainError("cross_tenant_access", "無法存取其他收容所資料", 404)
        if draft.volunteer_user_id != volunteer_user_id or draft.animal_id != animal.id:
            raise DomainError("draft_binding_mismatch", "草稿與目前操作不一致", 409)
        CareReportAnswers(dict(draft.answers))
        if self.note_validator is not None:
            self.note_validator(draft.answers, note if note is not None else draft.note)
        if self.answer_validator is not None:
            for field, value in draft.answers.items():
                if not isinstance(value, str):
                    raise DomainError("invalid_option", "回報選項格式無效", 422)
                # UNOBSERVED is a Bot-level marker, not a CRM code — the
                # validator only knows real vocabulary, so it must not see it.
                if value == UNOBSERVED:
                    continue
                self.answer_validator(field, value)
        if animal.status != "active":
            raise DomainError("animal_not_reportable", "動物目前不可回報", 409)
        if self.scope_validator is not None and not await self.scope_validator(animal.id):
            raise DomainError("animal_not_reportable", "動物目前不在你的今日可回報範圍", 403)
        report = await self.reports.add(
            CareReport(
                organization_id=draft.organization_id,
                draft_id=draft.id,
                animal_id=animal.id,
                volunteer_user_id=volunteer_user_id,
                membership_id=draft.membership_id,
                answers=dict(draft.answers),
                answer_snapshots=self.answer_snapshots,
                animal_name_snapshot=animal.name,
                shelter_number_snapshot=animal.shelter_number,
                note=note if note is not None else draft.note,
                story=story if story is not None else draft.story,
                status="saved",
                ai_job_status="pending_enqueue",
                submitted_at=datetime.now(timezone.utc),
            )
        )
        await self.reports.add_idempotency(
            volunteer_user_id=volunteer_user_id, key=idempotency_key, report_id=report.id
        )
        await self.reports.attach_media(
            report_id=report.id,
            media_asset_ids=media_asset_ids or await self.drafts.media_ids(draft.id),
        )
        if self.usage_service is not None:
            try:
                await self.usage_service.index_report(report, snapshots=report.answer_snapshots)
            except Exception:
                # The CRM report is authoritative; a rebuildable index must never
                # make an otherwise valid volunteer report fail.
                pass
        if self.audit is not None:
            await self.audit.record(
                organization_id=report.organization_id,
                actor_user_id=volunteer_user_id,
                action="care_report.submitted",
                resource_type="care_report",
                resource_id=report.id,
                source_channel="line_bot",
                after={"animal_id": report.animal_id, "draft_id": draft.id},
            )
        draft.status = "submitted"
        draft.current_step = "submitted"
        return report
