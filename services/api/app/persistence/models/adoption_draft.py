from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class AdoptionDraft(IdentityMixin, AuditMixin, Base):
    __tablename__ = "adoption_drafts"

    opaque_token_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Nullable unlike every other tenant-scoped table: the very first turn
    # (SELECTING_ORGANIZATION) happens before the adopter has picked a shelter.
    # See migration 0030's RLS policy comment before copying this pattern elsewhere.
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    adopter_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    path: Mapped[str | None] = mapped_column(String(30), nullable=True)
    target_animal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("animals.id"), nullable=True, index=True
    )
    candidate_match_ids: Mapped[list] = mapped_column(JSON, default=list)
    # [{"animal_id": str, "score": float, "reasons": [str, ...]}, ...] — one
    # entry for the specific_animal path, up to top_n for recommend_me.
    match_results: Mapped[list] = mapped_column(JSON, default=list)
    current_step: Mapped[str] = mapped_column(
        String(50), default="selecting_organization", index=True
    )
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    reconfirmation_keys: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    last_interaction_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Populated asynchronously by the background Gemini suitability analysis
    # task — nullable/additive so a draft is already usable before this
    # fills in (or forever, if Gemini isn't configured / the call fails).
    ai_suitability_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_suitability_explanation: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Non-NULL means: the adopter was just asked a free-text follow-up
    # question about special requirements for THIS animal (because its AI
    # score came back below 60%), and the next non-phone-number text message
    # they send should be treated as that answer, not a stray/invalid input.
    # Cleared as soon as that answer is received (or a new AI analysis runs).
    ai_followup_target_animal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("animals.id"), nullable=True
    )
    # How many AWAITING_FREETEXT_PROFILE rounds have been consumed — see
    # AdoptionDraftStateMachine.freetext_profile_rounds /
    # AWAITING_FREETEXT_PROFILE_MAX_ROUNDS.
    freetext_profile_rounds: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
