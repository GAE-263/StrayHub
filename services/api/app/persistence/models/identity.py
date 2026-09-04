from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin, utc_now


class Organization(IdentityMixin, AuditMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    service_area: Mapped[str | None] = mapped_column(String(200), nullable=True)
    region: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    contact: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_setup", index=True)
    timezone: Mapped[str] = mapped_column(
        String(64), default="Asia/Taipei", server_default="Asia/Taipei", nullable=False
    )
    timezone_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )


class User(IdentityMixin, AuditMixin, Base):
    __tablename__ = "users"

    username: Mapped[str | None] = mapped_column(
        String(200), unique=True, nullable=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    platform_role: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)


class OrganizationMembership(IdentityMixin, AuditMixin, Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_organization_memberships_org_id"),
        CheckConstraint(
            "role <> 'VOLUNTEER' OR "
            "(valid_from IS NOT NULL AND expires_at IS NOT NULL AND expires_at > valid_from)",
            name="ck_organization_memberships_volunteer_finite_period",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    volunteer_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    can_assist_new_volunteers: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    archived_from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    access_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    medical_care_access: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )


class SessionRecord(IdentityMixin, AuditMixin, Base):
    __tablename__ = "session_records"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    active_organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RefreshTokenRecord(IdentityMixin, AuditMixin, Base):
    __tablename__ = "refresh_token_records"

    session_id: Mapped[UUID] = mapped_column(ForeignKey("session_records.id"), index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LineUserBinding(IdentityMixin, AuditMixin, Base):
    __tablename__ = "line_user_bindings"

    line_user_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)


class WebhookSession(IdentityMixin, AuditMixin, Base):
    __tablename__ = "webhook_sessions"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LineWebhookEvent(IdentityMixin, Base):
    __tablename__ = "line_webhook_events"

    webhook_event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    processing_status: Mapped[str] = mapped_column(String(30), default="received")
    redelivery: Mapped[bool] = mapped_column(Boolean, default=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
