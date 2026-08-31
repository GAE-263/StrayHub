from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class AdoptionInquiry(IdentityMixin, AuditMixin, Base):
    __tablename__ = "adoption_inquiries"

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    draft_id: Mapped[UUID] = mapped_column(
        ForeignKey("adoption_drafts.id"), unique=True, index=True
    )
    adopter_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    path: Mapped[str] = mapped_column(String(30))
    target_animal_id: Mapped[UUID] = mapped_column(ForeignKey("animals.id"), index=True)
    animal_name_snapshot: Mapped[str] = mapped_column(String(200))
    shelter_number_snapshot: Mapped[str | None] = mapped_column(String(120), nullable=True)
    answers: Mapped[dict] = mapped_column(JSON)
    match_scores_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Extracted from `answers["adopter_name"]` / `answers["phone_number"]` at
    # submit time for easy filtering/display in the staff inbox; immutable
    # once submitted (unlike the draft's copy). `contact_time` stays only in
    # `answers` — less staff-facing need to filter/search on it than a name
    # or phone number.
    adopter_name: Mapped[str] = mapped_column(String(100), server_default="")
    phone_number: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    staff_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status_updated_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # Copied from the draft's fields at submit time, if the (not-yet-wired)
    # Gemini analysis had completed before submission — see AdoptionDraft.
    ai_suitability_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_suitability_explanation: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # The later of "a 毛孩日記 reminder was last pushed" and "the adopter last
    # submitted an entry on their own" — either resets the reminder cadence
    # clock, so a scheduled nudge never fires right after the adopter already
    # shared an update unprompted. NULL means neither has happened yet, so
    # `services.api.app.domain.growth_diary_reminder` falls back to
    # `submitted_at` (the adoption date) as the clock's start.
    last_growth_diary_prompted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
