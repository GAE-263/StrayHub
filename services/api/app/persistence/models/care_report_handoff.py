from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class CareReportHandoff(IdentityMixin, AuditMixin, Base):
    __tablename__ = "care_report_handoffs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'consumed', 'expired', 'superseded')",
            name="ck_care_report_handoffs_status",
        ),
        CheckConstraint(
            "source IN ('liff_scan', 'qr_deeplink', 'shelter_number')",
            name="ck_care_report_handoffs_source",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_care_report_handoffs_expiry",
        ),
        Index(
            "uq_care_report_handoffs_pending_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    membership_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization_memberships.id"), index=True
    )
    animal_id: Mapped[UUID] = mapped_column(ForeignKey("animals.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(30))
