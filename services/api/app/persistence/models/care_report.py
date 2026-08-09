from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin, utc_now


class MediaAsset(IdentityMixin, AuditMixin, Base):
    __tablename__ = "media_assets"

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="processed", index=True)
    purpose: Mapped[str | None] = mapped_column(String(80), nullable=True)
    exif_removed: Mapped[bool] = mapped_column(default=True)


class CareReport(IdentityMixin, AuditMixin, Base):
    __tablename__ = "care_reports"

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    draft_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("care_report_drafts.id"), nullable=True, unique=True, index=True
    )
    animal_id: Mapped[UUID] = mapped_column(ForeignKey("animals.id"), index=True)
    volunteer_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    membership_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization_memberships.id"), index=True
    )
    answers: Mapped[dict] = mapped_column(JSON)
    answer_snapshots: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    animal_name_snapshot: Mapped[str] = mapped_column(String(200))
    shelter_number_snapshot: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(String(5000), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="saved", index=True)
    ai_job_status: Mapped[str] = mapped_column(String(30), default="pending_enqueue")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    archive_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class CareReportMedia(IdentityMixin, Base):
    __tablename__ = "care_report_media"

    report_id: Mapped[UUID] = mapped_column(ForeignKey("care_reports.id"), index=True)
    media_asset_id: Mapped[UUID] = mapped_column(ForeignKey("media_assets.id"), index=True)


class ReportIdempotencyKey(IdentityMixin, Base):
    __tablename__ = "report_idempotency_keys"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "volunteer_user_id", "key", name="uq_report_idempotency_scope"
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    volunteer_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    key: Mapped[str] = mapped_column(String(200))
    report_id: Mapped[UUID] = mapped_column(ForeignKey("care_reports.id"))


class CareReportCorrection(IdentityMixin, Base):
    __tablename__ = "care_report_corrections"

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    report_id: Mapped[UUID] = mapped_column(ForeignKey("care_reports.id"), index=True)
    actor_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    original_animal_id: Mapped[UUID] = mapped_column(ForeignKey("animals.id"))
    corrected_animal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("animals.id"), nullable=True
    )
    before_data: Mapped[dict] = mapped_column(JSON)
    after_data: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
