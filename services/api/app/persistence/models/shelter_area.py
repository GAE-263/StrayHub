from uuid import UUID

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class ShelterArea(IdentityMixin, AuditMixin, Base):
    __tablename__ = "shelter_areas"

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    area_type: Mapped[str] = mapped_column(String(40), default="area")
    parent_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
