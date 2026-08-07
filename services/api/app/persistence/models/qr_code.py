from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class AnimalQrCode(IdentityMixin, AuditMixin, Base):
    __tablename__ = "animal_qr_codes"

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    animal_id: Mapped[UUID] = mapped_column(ForeignKey("animals.id"), index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
