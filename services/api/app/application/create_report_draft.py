from __future__ import annotations

from uuid import UUID

from services.api.app.application.line_draft_service import LineDraftService
from services.api.app.persistence.models.care_report_draft import CareReportDraft
from services.api.app.persistence.repositories.care_report_draft_repository import (
    CareReportDraftRepository,
)


class CreateReportDraftService:
    """在動物確認完成後建立固定租戶與動物關聯的 Server-side Draft。"""

    def __init__(self, repository: CareReportDraftRepository, *, ttl_seconds: int = 86400) -> None:
        self.service = LineDraftService(repository, ttl_seconds=ttl_seconds)

    async def create(
        self, *, volunteer_user_id: UUID, membership_id: UUID, animal_id: UUID
    ) -> tuple[CareReportDraft, str]:
        return await self.service.create(
            volunteer_user_id=volunteer_user_id,
            membership_id=membership_id,
            animal_id=animal_id,
        )
