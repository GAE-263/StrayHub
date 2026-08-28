from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class GrowthDiaryDraft(AuditMixin, Base):
    """One row per adopter mid-flow: exists only between tapping 毛孩成長日記
    (or picking which adopted pet) and sending the photo/text that completes
    the entry — deleted once saved. A pending marker, not a multi-step state
    machine, matching how minimal this first version of the flow is."""

    __tablename__ = "growth_diary_drafts"

    adopter_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    inquiry_id: Mapped[UUID] = mapped_column(ForeignKey("adoption_inquiries.id"))
    animal_id: Mapped[UUID] = mapped_column(ForeignKey("animals.id"))


class GrowthDiaryEntry(IdentityMixin, AuditMixin, Base):
    __tablename__ = "growth_diary_entries"

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    inquiry_id: Mapped[UUID] = mapped_column(ForeignKey("adoption_inquiries.id"), index=True)
    animal_id: Mapped[UUID] = mapped_column(ForeignKey("animals.id"), index=True)
    adopter_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    photo_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
