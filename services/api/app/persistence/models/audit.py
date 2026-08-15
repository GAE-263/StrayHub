from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import Base, IdentityMixin, utc_now


class AuditRecord(IdentityMixin, Base):
    __tablename__ = "audit_records"
    __table_args__ = (
        CheckConstraint(
            "(actor_type = 'user' AND actor_user_id IS NOT NULL "
            "AND actor_reference IS NULL) OR "
            "(actor_type = 'system' AND actor_user_id IS NULL "
            "AND actor_reference IS NOT NULL AND length(trim(actor_reference)) > 0)",
            name="ck_audit_records_actor_identity",
        ),
        Index(
            "ix_audit_records_org_actor_reference_created",
            "organization_id",
            "actor_type",
            "actor_reference",
            "created_at",
        ),
    )

    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_type: Mapped[str] = mapped_column(
        String(20), default="user", server_default="user", nullable=False
    )
    actor_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    operation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        default=uuid4,
        server_default=text("md5(random()::text || clock_timestamp()::text)::uuid"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(120))
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    source_channel: Mapped[str] = mapped_column(String(30))
    before_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    result: Mapped[str] = mapped_column(String(30), default="success", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
