from datetime import date
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class Animal(IdentityMixin, AuditMixin, Base):
    __tablename__ = "animals"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_animals_org_id"),
        CheckConstraint("sex IN ('male', 'female', 'unknown')", name="ck_animals_sex"),
        CheckConstraint("birth_date <= intake_date", name="ck_animals_birth_intake"),
        CheckConstraint(
            "NOT birth_date_estimated OR birth_date IS NOT NULL", name="ck_animals_estimated_birth"
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    shelter_number: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    current_photo_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    area_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("shelter_areas.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    sex: Mapped[str] = mapped_column(String(10), default="unknown", server_default="unknown")
    breed: Mapped[str | None] = mapped_column(String(120), nullable=True)
    intake_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    birth_date_estimated: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    age_description: Mapped[str | None] = mapped_column(String(120), nullable=True)
    behavior_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    care_guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
