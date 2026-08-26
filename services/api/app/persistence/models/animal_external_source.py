from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class AnimalExternalSource(IdentityMixin, AuditMixin, Base):
    __tablename__ = "animal_external_sources"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_animal_external_identity"),
        UniqueConstraint("animal_id", "source", name="uq_animal_external_mapping"),
        ForeignKeyConstraint(
            ["organization_id", "animal_id"],
            ["animals.organization_id", "animals.id"],
            name="fk_external_animal_tenant",
        ),
        CheckConstraint("source = 'MOA_ADOPTION_OPEN_DATA'", name="ck_animal_external_source"),
        CheckConstraint(
            "source_status IN ('present', 'unavailable')", name="ck_animal_external_status"
        ),
        CheckConstraint(
            "octet_length(source_snapshot::text) <= 32768", name="ck_animal_external_snapshot_size"
        ),
        Index("ix_animal_external_org_status", "organization_id", "source", "source_status"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    animal_id: Mapped[UUID] = mapped_column()
    source: Mapped[str] = mapped_column(String(40))
    external_id: Mapped[str] = mapped_column(String(80))
    source_shelter_id: Mapped[str] = mapped_column(String(40))
    source_updated_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_status: Mapped[str] = mapped_column(String(20), default="present")
    source_snapshot: Mapped[dict] = mapped_column(JSONB)
    photo_source_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    photo_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
