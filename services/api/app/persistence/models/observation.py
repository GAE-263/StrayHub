from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class ObservationCategory(IdentityMixin, AuditMixin, Base):
    __tablename__ = "observation_categories"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_observation_category_scope_code"),
    )

    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(80))
    display_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class ObservationOption(IdentityMixin, AuditMixin, Base):
    __tablename__ = "observation_options"
    __table_args__ = (
        UniqueConstraint("category_id", "code", name="uq_observation_option_category_code"),
        CheckConstraint(
            "status IN ('active', 'disabled', 'archived')",
            name="ck_observation_options_status",
        ),
    )

    category_id: Mapped[UUID] = mapped_column(ForeignKey("observation_categories.id"), index=True)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    requires_note: Mapped[bool] = mapped_column(Boolean, default=False)
