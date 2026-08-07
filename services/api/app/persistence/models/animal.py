from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class Animal(IdentityMixin, AuditMixin, Base):
    __tablename__ = "animals"

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    shelter_number: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    current_photo_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    area_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("shelter_areas.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
