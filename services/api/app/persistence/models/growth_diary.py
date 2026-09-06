from datetime import date
from uuid import UUID

from sqlalchemy import JSON, Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class GrowthDiaryDraft(AuditMixin, Base):
    """One row per adopter, created the first time they tap 毛孩日記 (or pick
    which adopted pet) — no longer deleted once an entry is saved. It now
    doubles as "today's open thread": `current_entry_id`/`entry_date` point
    at whichever GrowthDiaryEntry same-day messages should append to (see
    _handle_growth_diary_message). Explicit "取消" is still the only thing
    that deletes the row outright, mid-way through composing a not-yet-saved
    entry. Still a pending marker, not a multi-step state machine — matching
    how minimal this flow's design otherwise stays."""

    __tablename__ = "growth_diary_drafts"

    adopter_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    inquiry_id: Mapped[UUID] = mapped_column(ForeignKey("adoption_inquiries.id"))
    animal_id: Mapped[UUID] = mapped_column(ForeignKey("animals.id"))
    # Which entry today's messages append to, and which calendar day (in the
    # organization's timezone) that entry was opened on — None until the
    # first message of a thread is saved. Reset to None whenever the adopter
    # switches to a different animal (see set_pending_draft), so a same-day
    # switch never appends into the wrong pet's entry.
    current_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("growth_diary_entries.id"), nullable=True
    )
    entry_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class GrowthDiaryEntry(IdentityMixin, AuditMixin, Base):
    """One row per *day* of shared updates for a given adopted animal, not
    one row per message — everything the adopter sends the same calendar day
    (in the organization's timezone) accumulates onto the same row (`note`
    grows by appending each new message's text; `photo_keys` grows by one
    entry per photo shared), and the next calendar day's first message opens
    a brand new row. See _handle_growth_diary_message/GrowthDiaryRepository.
    append_to_entry for where that merge happens."""

    __tablename__ = "growth_diary_entries"

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    inquiry_id: Mapped[UUID] = mapped_column(ForeignKey("adoption_inquiries.id"), index=True)
    animal_id: Mapped[UUID] = mapped_column(ForeignKey("animals.id"), index=True)
    adopter_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # Every photo shared this day, oldest first — AI analysis only looks at
    # photo_keys[-1] (the latest) to keep the multimodal call cheap and
    # simple, but every photo is still kept and shown in the staff inbox.
    photo_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
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
    # Staff inbox read/processed marker — "new" until a staff member marks it
    # "reviewed" via the management UI (see GrowthDiaryInboxService.set_status).
    # No workflow beyond these two values yet (minimal first version).
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
