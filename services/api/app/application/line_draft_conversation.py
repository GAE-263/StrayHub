from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.application.report_submission import ReportSubmissionService
from services.api.app.domain.line_care_report_state import (
    DraftAnswers,
    DraftState,
    DraftStateMachine,
)
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.care_report_draft_repository import (
    CareReportDraftRepository,
)
from services.api.app.persistence.repositories.care_report_repository import CareReportRepository
from services.api.app.persistence.repositories.reportable_scope_repository import (
    ReportableScopeRepository,
)


@dataclass(frozen=True)
class ConversationResult:
    state: DraftState
    report_id: UUID | None = None


class LineDraftConversationService:
    """在 CRM Draft 上執行 Bot 對話，不信任 Postback 的 step 或權限欄位。"""

    def __init__(
        self,
        draft_repository: CareReportDraftRepository,
        *,
        answer_validator: Callable[[str, str], None] | None = None,
        note_validator: Callable[[dict[str, str], str | None], None] | None = None,
    ) -> None:
        self.draft_repository = draft_repository
        self.answer_validator = answer_validator
        self.note_validator = note_validator

    async def handle(
        self,
        *,
        token: str | None,
        volunteer_user_id: UUID,
        action: str,
        value: str | None,
        event_id: str,
    ) -> ConversationResult:
        draft = (
            await self.draft_repository.get_by_token(token)
            if token
            else await self.draft_repository.get_active_for_volunteer(volunteer_user_id)
        )
        if (
            draft is None
            or draft.volunteer_user_id != volunteer_user_id
            or draft.status != "active"
        ):
            raise DomainError("draft_access_denied", "草稿不存在或無法存取", 404)
        if draft.expires_at <= datetime.now(timezone.utc):
            draft.status = "expired"
            draft.current_step = DraftState.EXPIRED.value
            raise DomainError("draft_expired", "草稿已過期", 409)

        machine = DraftStateMachine(
            state=DraftState(draft.current_step),
            answers=DraftAnswers(dict(draft.answers)),
            reconfirmation_keys=set(getattr(draft, "reconfirmation_keys", []) or []),
        )
        report_id = None
        if action == "confirm_animal":
            machine.transition(DraftState.ANSWERING_COMPLETION)
        elif action == "back":
            machine.back()
        elif action == "answer":
            if value is None:
                raise DomainError("answer_required", "需要選擇回報答案", 422)
            if self.answer_validator is not None:
                self.answer_validator(machine.next_answer_key(), value)
            machine.answer_current(value)
        elif action == "skip_media":
            machine.transition(DraftState.AWAITING_NOTE)
        elif action == "skip_note":
            machine.transition(DraftState.REVIEWING)
        elif action == "note":
            if machine.state != DraftState.AWAITING_NOTE or value is None:
                raise DomainError("invalid_note_step", "目前步驟不接受心得", 409)
            draft.note = value
            machine.transition(DraftState.REVIEWING)
        elif action in {"submit", "submit_current"}:
            machine.transition(DraftState.SUBMITTING)
            machine.submit()
            animal = await AnimalRepository(
                self.draft_repository.session,
                self.draft_repository.organization_id,
            ).get(draft.animal_id)
            if animal is None or animal.status != "active":
                raise DomainError("animal_not_found", "動物不存在或無法回報", 404)
            if not await ReportableScopeRepository(
                self.draft_repository.session,
                self.draft_repository.organization_id,
            ).is_animal_reportable(
                animal_id=animal.id,
                volunteer_user_id=volunteer_user_id,
            ):
                raise DomainError("animal_not_reportable", "動物目前不在你的今日可回報範圍", 403)
            report = await ReportSubmissionService(
                self.draft_repository,
                CareReportRepository(
                    self.draft_repository.session,
                    self.draft_repository.organization_id,
                ),
                answer_validator=self.answer_validator,
                audit=AuditService(self.draft_repository.session),
                note_validator=self.note_validator,
            ).submit(
                draft_id=draft.id,
                volunteer_user_id=volunteer_user_id,
                animal=animal,
                idempotency_key=event_id,
                note=draft.note,
                media_asset_ids=await self.draft_repository.media_ids(draft.id),
            )
            report_id = report.id
        elif action in {"cancel", "cancel_current"}:
            machine.transition(DraftState.CANCELLED)
        else:
            raise DomainError("invalid_postback_action", "目前步驟不允許此操作", 409)

        draft.answers = dict(machine.answers.values)
        draft.reconfirmation_keys = sorted(machine.reconfirmation_keys)
        draft.current_step = machine.state.value
        if machine.state == DraftState.SUBMITTED:
            draft.status = "submitted"
        elif machine.state == DraftState.CANCELLED:
            draft.status = "cancelled"
        elif machine.state == DraftState.EXPIRED:
            draft.status = "expired"
        draft.last_interaction_at = datetime.now(timezone.utc)
        await self.draft_repository.session.flush()
        return ConversationResult(state=machine.state, report_id=report_id)

    async def note_for_current(
        self,
        *,
        volunteer_user_id: UUID,
        note: str,
    ) -> ConversationResult:
        draft = await self.draft_repository.get_active_for_volunteer(volunteer_user_id)
        if draft is None or draft.current_step != DraftState.AWAITING_NOTE.value:
            raise DomainError("invalid_note_step", "目前沒有可填寫心得的回報", 409)
        machine = DraftStateMachine(
            state=DraftState(draft.current_step),
            answers=DraftAnswers(dict(draft.answers)),
            reconfirmation_keys=set(getattr(draft, "reconfirmation_keys", []) or []),
        )
        if not note.strip():
            raise DomainError("note_required", "心得內容不可為空", 422)
        draft.note = note[:5000]
        machine.transition(DraftState.REVIEWING)
        draft.current_step = machine.state.value
        draft.last_interaction_at = datetime.now(timezone.utc)
        await self.draft_repository.session.flush()
        return ConversationResult(state=machine.state)
