from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin, utc_now


class Organization(IdentityMixin, AuditMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    service_area: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_setup", index=True)


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

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)


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
