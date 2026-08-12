from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import Base, IdentityMixin, utc_now


class ObservationOptionUsage(IdentityMixin, Base):
    """Rebuildable index of observation codes used by an official care report."""

    __tablename__ = "observation_option_usages"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "care_report_id",
            "option_code",
            name="uq_observation_option_usage_report_code",
        ),
        Index("ix_observation_option_usage_org_code", "organization_id", "option_code"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    care_report_id: Mapped[UUID] = mapped_column(
        ForeignKey("care_reports.id"), nullable=False, index=True
    )
    observation_option_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("observation_options.id"), nullable=True, index=True
    )
    category_code: Mapped[str] = mapped_column(String(80), nullable=False)
    option_code: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
