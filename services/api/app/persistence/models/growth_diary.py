from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class GrowthDiaryDraft(AuditMixin, Base):
    """One row per adopter mid-flow: exists only between tapping 毛孩日記
    (or picking which adopted pet) and sending the photo/text that completes
    the entry — deleted once saved. A pending marker, not a multi-step state
    machine, matching how minimal this first version of the flow is."""

    __tablename__ = "growth_diary_drafts"

    adopter_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    inquiry_id: Mapped[UUID] = mapped_column(ForeignKey("adoption_inquiries.id"))
    animal_id: Mapped[UUID] = mapped_column(ForeignKey("animals.id"))
    current_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("growth_diary_entries.id"), nullable=True
    )
    entry_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class GrowthDiaryEntry(IdentityMixin, AuditMixin, Base):
    __tablename__ = "growth_diary_entries"

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    inquiry_id: Mapped[UUID] = mapped_column(ForeignKey("adoption_inquiries.id"), index=True)
    animal_id: Mapped[UUID] = mapped_column(ForeignKey("animals.id"), index=True)
    adopter_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    photo_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    photo_keys: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    entry_date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("CURRENT_DATE"), index=True
    )
    content_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="new", server_default="new", index=True
    )
    status_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status_updated_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # Populated asynchronously by a background Gemini analysis task (see
    # growth_diary_ai_analysis_service.py) — nullable/additive so a row is
    # already visible (and the adopter's reply already sent) well before
    # these fill in; NULL forever if that background task never ran (no
    # Gemini credentials configured) or genuinely failed.
    ai_mood: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # positive|neutral|concern
    ai_reply: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    ai_staff_summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    ai_analysis_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_content_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ai_model_version: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ai_prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_output_schema_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_raw_output: Mapped[dict[str, Any] | str | None] = mapped_column(JSON, nullable=True)
    ai_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
