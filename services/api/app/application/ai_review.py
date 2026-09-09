from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.domain.report_summary import fingerprint, rule_summary, validate_summary
from services.api.app.persistence.models.care_report import CareReport
from services.api.app.persistence.repositories.ai_observation_repository import (
    AIObservationRepository,
)


class AIReviewService:
    def __init__(
        self, repository: AIObservationRepository, *, audit: AuditService | None = None
    ) -> None:
        self.repository = repository
        self.audit = audit

    async def review(
        self,
        observation_id: UUID,
        *,
        actor_user_id: UUID,
        action: str,
        result: dict | None = None,
        reason: str | None = None,
    ):
        if action not in {"confirm", "reject", "correct"}:
            raise DomainError("invalid_ai_review", "人工覆核動作無效", 422)
        if action == "correct" and not result:
            raise DomainError("ai_correction_required", "人工修正內容不可為空", 422)
        observation = await self.repository.get(observation_id)
        if observation is None:
            raise DomainError("observation_not_found", "AI Observation 不存在或無法存取", 404)
        if observation.status in {"failed", "invalid"}:
            raise DomainError("ai_review_unavailable", "目前 AI 結果不可覆核", 409)
        if getattr(observation, "source_type", None) == "care_report_summary":
            report = await self.repository.session.scalar(
                select(CareReport)
                .where(
                    CareReport.id == observation.source_id,
                    CareReport.organization_id == self.repository.organization_id,
                )
                .with_for_update()
            )
            if report is None or report.summary_fingerprint != fingerprint(report):
                raise DomainError("summary_stale", "回報已更正，不能覆核舊摘要", 409)
            if action == "correct":
                try:
                    result = validate_summary(json.dumps(result, ensure_ascii=False), report)
                except ValueError as exc:
                    raise DomainError("invalid_summary", "摘要格式或原文依據不符", 422) from exc
                report.summary_data = result
                report.attention_level = result["attention_level"]
                report.summary_status = "succeeded"
            elif action == "reject":
                report.summary_data = None
                report.summary_status = "rejected"
                report.attention_level = rule_summary(report)["attention_level"]
            elif action == "confirm":
                report.summary_data = observation.validated_ai_observation
                report.summary_status = "succeeded"
                report.attention_level = report.summary_data["attention_level"]
        before = {
            "status": observation.status,
            "raw_ai_output": observation.raw_ai_output,
            "validated_ai_observation": observation.validated_ai_observation,
            "human_review_result": observation.human_review_result,
        }
        observation.status = {
            "confirm": "confirmed",
            "reject": "rejected",
            "correct": "corrected",
        }[action]
        observation.human_review_result = {
            "action": action,
            "reason": reason,
            "result": result,
        }
        observation.reviewed_by = actor_user_id
        observation.reviewed_at = datetime.now(timezone.utc)
        if self.audit is not None:
            await self.audit.record(
                organization_id=observation.organization_id,
                actor_user_id=actor_user_id,
                action="ai_observation.reviewed",
                resource_type="AIObservation",
                resource_id=observation.id,
                source_channel="api",
                before=before,
                after={
                    "status": observation.status,
                    "human_review_result": observation.human_review_result,
                },
                reason=reason,
            )
        return observation
