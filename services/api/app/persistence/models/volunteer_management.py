"""Volunteer identity profile and shelter-scoped management records."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin, utc_now


class VolunteerProfile(AuditMixin, Base):
    """Canonical, non-identifying-key volunteer profile for one natural person."""

    __tablename__ = "volunteer_profiles"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    surname: Mapped[str | None] = mapped_column(String(20), nullable=True)
    preferred_display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)


class OrganizationVolunteerNumberCounter(AuditMixin, Base):
    __tablename__ = "organization_volunteer_number_counters"
    __table_args__ = (
        CheckConstraint("next_value > 0", name="ck_volunteer_number_counter_positive"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    next_value: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )


class VolunteerNote(IdentityMixin, AuditMixin, Base):
    __tablename__ = "volunteer_notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "subject_membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            name="fk_volunteer_notes_subject_membership_scope",
        ),
        ForeignKeyConstraint(
            ["organization_id", "author_membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            name="fk_volunteer_notes_author_membership_scope",
        ),
        CheckConstraint("length(trim(content)) > 0", name="ck_volunteer_notes_content"),
        Index(
            "ix_volunteer_notes_org_subject_created",
            "organization_id",
            "subject_membership_id",
            "created_at",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    subject_membership_id: Mapped[UUID] = mapped_column(index=True)
    author_membership_id: Mapped[UUID] = mapped_column(index=True)
    content: Mapped[str] = mapped_column(String(2000))


class VolunteerIncident(IdentityMixin, AuditMixin, Base):
    __tablename__ = "volunteer_incidents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "subject_membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            name="fk_volunteer_incidents_subject_membership_scope",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by_membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            name="fk_volunteer_incidents_creator_membership_scope",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_volunteer_incidents_severity",
        ),
        UniqueConstraint("organization_id", "id", name="uq_volunteer_incidents_org_id"),
        CheckConstraint(
            "status IN ('reported', 'under_review', 'confirmed', 'dismissed')",
            name="ck_volunteer_incidents_status",
        ),
        CheckConstraint(
            "length(trim(incident_type)) > 0 AND length(trim(factual_summary)) > 0",
            name="ck_volunteer_incidents_content",
        ),
        Index(
            "ix_volunteer_incidents_org_subject_occurred",
            "organization_id",
            "subject_membership_id",
            "occurred_at",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    subject_membership_id: Mapped[UUID] = mapped_column(index=True)
    volunteer_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    incident_type: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(20))
    factual_summary: Mapped[str] = mapped_column(String(2000))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_membership_id: Mapped[UUID] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20), default="reported")
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VolunteerRestriction(IdentityMixin, AuditMixin, Base):
    __tablename__ = "volunteer_restrictions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "incident_id"],
            ["volunteer_incidents.organization_id", "volunteer_incidents.id"],
            name="fk_volunteer_restrictions_incident_scope",
        ),
        ForeignKeyConstraint(
            ["organization_id", "requested_by_membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            name="fk_volunteer_restrictions_requester_scope",
        ),
        CheckConstraint("scope IN ('SHELTER', 'PLATFORM')", name="ck_volunteer_restrictions_scope"),
        CheckConstraint(
            "status IN ('pending_review', 'active', 'rejected', 'expired', 'revoked')",
            name="ck_volunteer_restrictions_status",
        ),
        CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at",
            name="ck_volunteer_restrictions_period",
        ),
        CheckConstraint(
            "status <> 'active' OR (approved_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_volunteer_restrictions_active_review",
        ),
        Index(
            "ix_volunteer_restrictions_subject_active",
            "volunteer_user_id",
            "scope",
            "status",
            "starts_at",
            "ends_at",
        ),
        Index("ix_volunteer_restrictions_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    volunteer_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    incident_id: Mapped[UUID] = mapped_column(index=True)
    scope: Mapped[str] = mapped_column(String(20))
    reason_category: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="pending_review")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_by_membership_id: Mapped[UUID] = mapped_column(index=True)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
