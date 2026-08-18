from sqlalchemy import CheckConstraint, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin


class PlatformAdminPolicy(IdentityMixin, AuditMixin, Base):
    """Singleton policy row and database lock point for platform-admin mutations."""

    __tablename__ = "platform_admin_policies"
    __table_args__ = (
        UniqueConstraint("policy_key", name="uq_platform_admin_policies_policy_key"),
        CheckConstraint("min_active_admins >= 1", name="ck_platform_admin_policy_min"),
        CheckConstraint(
            "max_active_admins >= min_active_admins",
            name="ck_platform_admin_policy_bounds",
        ),
    )

    policy_key: Mapped[str] = mapped_column(
        String(40), nullable=False, unique=True, default="default", server_default="default"
    )
    min_active_admins: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    max_active_admins: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, server_default=text("2")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
