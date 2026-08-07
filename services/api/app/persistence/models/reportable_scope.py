from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class DailyReportableScope(IdentityMixin, AuditMixin, Base):
    __tablename__ = "daily_reportable_scopes"
    __table_args__ = (
        CheckConstraint(
            "animal_id IS NOT NULL OR area_id IS NOT NULL",
            name="ck_reportable_scope_target",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    animal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("animals.id"), nullable=True, index=True
    )
    area_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("shelter_areas.id"), nullable=True, index=True
    )
    volunteer_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
