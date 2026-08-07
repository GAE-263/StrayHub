from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
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
    ):
        if action not in {"confirm", "reject", "correct"}:
            raise DomainError("invalid_ai_review", "人工覆核動作無效", 422)
        if action == "correct" and not result:
            raise DomainError("ai_correction_required", "人工修正內容不可為空", 422)
        observation = await self.repository.get(observation_id)
        if observation is None:
            raise DomainError("observation_not_found", "AI Observation 不存在或無法存取", 404)
        before = {
            "status": observation.status,
            "human_review_result": observation.human_review_result,
        }
        observation.status = {
            "confirm": "confirmed",
            "reject": "rejected",
            "correct": "corrected",
        }[action]
        observation.human_review_result = result or {"action": action}
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
            )
        return observation
