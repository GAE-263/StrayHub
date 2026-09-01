from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.domain.line_care_report_state import DraftState, DraftStateMachine


@dataclass
class InMemoryBotDraft:
    organization_id: UUID
    volunteer_user_id: UUID
    machine: DraftStateMachine


class LinePostbackService:
    """Stateful Bot command handler; payload values are candidates only."""

    def __init__(self) -> None:
        self.drafts: dict[str, InMemoryBotDraft] = {}
        self.processed_events: set[str] = set()

    def register_draft(self, token: str, draft: InMemoryBotDraft) -> None:
        self.drafts[token] = draft

    def current_state(self, token: str, *, organization_id: UUID) -> DraftState:
        draft = self.drafts.get(token)
        if draft is None or draft.organization_id != organization_id:
            raise DomainError("draft_access_denied", "草稿不存在或無法存取", 404)
        return draft.machine.state

    def handle(
        self,
        *,
        event_id: str,
        line_user_id: str,
        draft_token: str,
        action: str,
        value: str | None = None,
        organization_id: UUID,
    ) -> str:
        if event_id in self.processed_events:
            return "duplicate_ignored"
        draft = self.drafts.get(draft_token)
        if draft is None or draft.organization_id != organization_id:
            raise DomainError("draft_access_denied", "草稿不存在或無法存取", 404)
        if str(draft.volunteer_user_id) != line_user_id:
            raise DomainError("draft_access_denied", "草稿不存在或無法存取", 404)
        if action == "confirm":
            draft.machine.transition(DraftState.ANSWERING_WALK_COMPLETION)
        elif action == "back":
            draft.machine.back()
        elif action == "answer":
            if value is None:
                raise DomainError("answer_required", "需要選擇回報答案", 422)
            draft.machine.answer_current(value)
        elif (
            action == "skip_stool_media"
            and draft.machine.state == DraftState.AWAITING_STOOL_MEDIA
        ):
            draft.machine.transition(DraftState.ANSWERING_ANIMAL_INTERACTION)
        elif action == "skip_note" and draft.machine.state == DraftState.AWAITING_NOTE:
            draft.machine.transition(DraftState.AWAITING_STORY)
        elif action == "skip_story" and draft.machine.state == DraftState.AWAITING_STORY:
            draft.machine.transition(DraftState.REVIEWING)
        elif action == "submit" and draft.machine.state == DraftState.REVIEWING:
            draft.machine.transition(DraftState.SUBMITTING)
            draft.machine.submit()
        elif action == "cancel":
            draft.machine.transition(DraftState.CANCELLED)
        else:
            raise DomainError("invalid_postback_action", "目前步驟不允許此操作", 409)
        self.processed_events.add(event_id)
        return "processed"
