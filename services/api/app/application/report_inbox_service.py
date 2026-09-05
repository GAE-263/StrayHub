from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.domain.report_summary import answer_rows, fingerprint, rule_summary
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.ai_observation import AIObservation
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.care_report import CareReport, CareReportMedia, MediaAsset
from services.api.app.persistence.models.identity import OrganizationMembership, User
from services.api.app.persistence.repositories.observation_repository import ObservationRepository
from services.api.app.persistence.repositories.timeline_repository import TimelineRepository


class ReportInboxService:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    @staticmethod
    def payload(
        report: CareReport,
        *,
        animal: Animal | None = None,
        media_ids: list[str] | None = None,
    ) -> dict:
        summary = getattr(report, "summary_data", None)
        if getattr(report, "summary_fingerprint", None) != fingerprint(report):
            summary = None
        return {
            "id": str(report.id),
            "organization_id": str(report.organization_id),
            "animal_id": str(report.animal_id),
            "animal_name": animal.name if animal else report.animal_name_snapshot,
            "animal_name_snapshot": report.animal_name_snapshot,
            "shelter_number_snapshot": report.shelter_number_snapshot,
            "volunteer_user_id": str(report.volunteer_user_id),
            "membership_id": str(report.membership_id),
            "answers": report.answers,
            "observations": report.answers,
            "answer_snapshots": report.answer_snapshots,
            "note": report.note,
            "story": getattr(report, "story", None),
            "answer_rows": answer_rows(report),
            "summary": summary or rule_summary(report),
            "summary_status": getattr(report, "summary_status", None) or "not_requested",
            "review_status": getattr(report, "review_status", None) or "pending",
            "review_version": getattr(report, "review_version", None) or 0,
            "review_history": getattr(report, "review_history", None) or [],
            "status": report.status,
            "ai_job_status": report.ai_job_status,
            "submitted_at": report.submitted_at.isoformat(),
            "archived_at": report.archived_at.isoformat() if report.archived_at else None,
            "media_ids": media_ids or [],
        }

    async def list(
        self,
        *,
        from_date: date | None,
        to_date: date | None,
        animal_id: UUID | None,
        report_status: str | None,
        page: int,
        page_size: int,
        review_status: str | None = None,
        attention_level: str | None = None,
        query: str | None = None,
    ) -> dict:
        filters = [CareReport.organization_id == self.organization_id]
        if review_status:
            filters.append(CareReport.review_status == review_status)
        if attention_level:
            filters.append(CareReport.attention_level == attention_level)
        if query and query.strip():
            term = (
                "%"
                + query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                + "%"
            )
            filters.append(
                or_(
                    CareReport.animal_name_snapshot.ilike(term, escape="\\"),
                    CareReport.shelter_number_snapshot.ilike(term, escape="\\"),
                )
            )
        if from_date:
            filters.append(
                CareReport.submitted_at
                >= datetime.combine(from_date, time.min, tzinfo=ZoneInfo("Asia/Taipei"))
            )
        if to_date:
            filters.append(
                CareReport.submitted_at
                < datetime.combine(
                    to_date + timedelta(days=1), time.min, tzinfo=ZoneInfo("Asia/Taipei")
                )
            )
        if animal_id:
            filters.append(CareReport.animal_id == animal_id)
        if report_status:
            filters.append(CareReport.status == report_status)
        total = await self.session.scalar(select(func.count(CareReport.id)).where(*filters))
        rows = await self.session.execute(
            select(CareReport, Animal)
            .join(
                Animal,
                and_(
                    Animal.id == CareReport.animal_id,
                    Animal.organization_id == self.organization_id,
                ),
            )
            .where(*filters)
            .order_by(
                case(
                    (CareReport.review_status == "pending", 0),
                    (CareReport.review_status == "follow_up", 1),
                    else_=2,
                ),
                case(
                    (CareReport.attention_level == "urgent", 0),
                    (CareReport.attention_level == "review", 1),
                    else_=2,
                ),
                CareReport.submitted_at.desc(),
                CareReport.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        pairs = rows.all()
        labels = await TimelineRepository(self.session, self.organization_id).volunteer_labels(
            [report.membership_id for report, _ in pairs]
        )
        items = []
        for report, animal in pairs:
            item = self.payload(report, animal=animal)
            surname, number = labels.get(report.membership_id, (None, None))
            item["volunteer_label"] = "・".join(
                value for value in (surname or "志工", number) if value
            )
            items.append(item)
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": int(total or 0),
        }

    async def process(
        self, report_id: UUID, *, actor_user_id: UUID, status: str, note: str, expected_version: int
    ) -> dict:
        report = await self.session.scalar(
            select(CareReport)
            .where(
                CareReport.id == report_id,
                CareReport.organization_id == self.organization_id,
            )
            .with_for_update()
        )
        if report is None:
            raise DomainError("report_not_found", "照護回報不存在或無法存取", 404)
        if report.status == "archived":
            raise DomainError("report_archived", "已封存回報不可更新處理狀態", 409)
        if report.review_version != expected_version:
            raise DomainError("report_review_conflict", "同事已更新此回報，請重新載入後再操作", 409)
        if status not in {"acknowledged", "follow_up", "resolved"}:
            raise DomainError("invalid_review_status", "處理狀態無效", 422)
        if status == "resolved" and report.review_status != "follow_up":
            raise DomainError("invalid_review_transition", "需追蹤的回報才能標記追蹤完成", 409)
        if status in {"follow_up", "resolved"} and not note.strip():
            raise DomainError("review_note_required", "請填寫追蹤事項或處理結果", 422)
        before = report.review_status
        actor_label = await self.session.scalar(
            select(User.display_name)
            .join(
                OrganizationMembership,
                OrganizationMembership.user_id == User.id,
            )
            .where(
                User.id == actor_user_id,
                OrganizationMembership.organization_id == self.organization_id,
            )
            .limit(1)
        )
        event = {
            "from_status": before,
            "status": status,
            "note": note.strip(),
            "actor_user_id": str(actor_user_id),
            "actor_label": actor_label or "平台管理員",
            "at": datetime.now(timezone.utc).isoformat(),
        }
        report.review_history = [*(report.review_history or []), event]
        report.review_status = status
        report.review_version += 1
        await AuditService(self.session).record(
            organization_id=self.organization_id,
            actor_user_id=actor_user_id,
            action="care_report.processed",
            resource_type="CareReport",
            resource_id=report.id,
            source_channel="api",
            before={"status": before},
            after=event,
            reason=note.strip(),
        )
        await self.session.flush()
        return self.payload(report)

    async def detail(self, report_id: UUID) -> dict:
        row = await self.session.execute(
            select(CareReport, Animal)
            .join(
                Animal,
                and_(
                    Animal.id == CareReport.animal_id,
                    Animal.organization_id == self.organization_id,
                ),
            )
            .where(
                CareReport.id == report_id,
                CareReport.organization_id == self.organization_id,
            )
        )
        pair = row.one_or_none()
        if pair is None:
            raise DomainError("report_not_found", "照護回報不存在或無法存取", 404)
        report, animal = pair
        media = await self.session.execute(
            select(MediaAsset)
            .join(CareReportMedia, CareReportMedia.media_asset_id == MediaAsset.id)
            .where(
                CareReportMedia.report_id == report_id,
                MediaAsset.organization_id == self.organization_id,
            )
        )
        ai = await self.session.execute(
            select(AIObservation, AIProcessingJob)
            .join(AIProcessingJob, AIProcessingJob.id == AIObservation.job_id)
            .where(
                AIObservation.organization_id == self.organization_id,
                AIProcessingJob.organization_id == self.organization_id,
                AIProcessingJob.target_type == "care_report",
                AIProcessingJob.target_id == report_id,
            )
        )
        payload = self.payload(
            report,
            animal=animal,
            media_ids=[str(item.id) for item in media.scalars()],
        )
        labels = await TimelineRepository(self.session, self.organization_id).volunteer_labels(
            [report.membership_id]
        )
        surname, number = labels.get(report.membership_id, (None, None))
        payload["volunteer_label"] = "・".join(
            value for value in (surname or "志工", number) if value
        )
        options = await ObservationRepository(self.session, self.organization_id).effective_options(
            include_disabled_history=False
        )
        payload["correction_options"] = [
            {"code": option.code, "label": option.display_name} for option in options
        ]
        payload["ai_observations"] = [
            {
                "id": str(observation.id),
                "status": observation.status,
                "source_type": observation.source_type,
                "source_id": str(observation.source_id) if observation.source_id else None,
                "raw_ai_output": observation.raw_ai_output,
                "validated_ai_observation": observation.validated_ai_observation,
                "human_review_result": observation.human_review_result,
                "failure_reason": job.failure_reason,
            }
            for observation, job in ai.all()
        ]
        return payload
