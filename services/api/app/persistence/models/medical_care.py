from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin, utc_now


class MedicalRecordType(StrEnum):
    VISIT = "visit"
    MEDICATION = "medication"
    VACCINATION = "vaccination"
    EXAMINATION = "examination"
    WEIGHT = "weight"
    SURGERY = "surgery"
    OTHER = "other"


class ReminderType(StrEnum):
    MEDICATION = "medication"
    FOLLOW_UP = "follow_up"
    WEIGHT = "weight"
    VACCINATION = "vaccination"
    EXAMINATION = "examination"
    OTHER = "other"


class ReminderFrequency(StrEnum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class ReminderSeriesStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    STOPPED = "stopped"


class OccurrenceStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ReminderActionType(StrEnum):
    CREATED_OVERRIDE = "created_override"
    RESCHEDULED = "rescheduled"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class MedicalRecord(IdentityMixin, AuditMixin, Base):
    __tablename__ = "medical_records"
    __table_args__ = (
        Index(
            "ix_medical_records_org_animal_occurred", "organization_id", "animal_id", "occurred_at"
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    animal_id: Mapped[UUID] = mapped_column(ForeignKey("animals.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    occurred_timezone: Mapped[str] = mapped_column(String(64), default="Asia/Taipei")
    record_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    clinic: Mapped[str | None] = mapped_column(String(300), nullable=True)
    veterinarian: Mapped[str | None] = mapped_column(String(200), nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Numeric(8, 3), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    archived_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class MedicalRecordMedia(IdentityMixin, Base):
    __tablename__ = "medical_record_media"
    __table_args__ = (UniqueConstraint("organization_id", "medical_record_id", "media_asset_id"),)

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    medical_record_id: Mapped[UUID] = mapped_column(ForeignKey("medical_records.id"), index=True)
    media_asset_id: Mapped[UUID] = mapped_column(ForeignKey("media_assets.id"), index=True)
    attached_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    attached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CareReminderSeries(IdentityMixin, AuditMixin, Base):
    __tablename__ = "care_reminder_series"
    __table_args__ = (
        Index("ix_care_series_org_status_animal", "organization_id", "status", "animal_id"),
    )

    lineage_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    animal_id: Mapped[UUID] = mapped_column(ForeignKey("animals.id"), index=True)
    reminder_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    assignee_membership_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organization_memberships.id"), nullable=True, index=True
    )
    anchor_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    anchor_local_time: Mapped[time] = mapped_column(Time, nullable=False)
    start_ordinal: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    end_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    interval: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    end_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    supersedes_series_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("care_reminder_series.id"), nullable=True
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspend_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class CareReminderOccurrence(IdentityMixin, AuditMixin, Base):
    __tablename__ = "care_reminder_occurrences"
    __table_args__ = (
        UniqueConstraint("organization_id", "lineage_id", "occurrence_index"),
        Index(
            "ix_care_occurrences_org_scheduled_status", "organization_id", "scheduled_at", "status"
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    lineage_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    series_id: Mapped[UUID] = mapped_column(ForeignKey("care_reminder_series.id"), index=True)
    occurrence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    nominal_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    nominal_local_time: Mapped[time] = mapped_column(Time, nullable=False)
    original_scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    timezone_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    assignee_membership_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organization_memberships.id"), nullable=True
    )
    title_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    instructions_snapshot: Mapped[str] = mapped_column(
        Text, default="", server_default="", nullable=False
    )
    type_snapshot: Mapped[str] = mapped_column(String(30), nullable=False)
    actual_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    result_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_action_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )


class CareReminderAction(IdentityMixin, Base):
    __tablename__ = "care_reminder_actions"
    __table_args__ = (
        UniqueConstraint("organization_id", "actor_user_id", "idempotency_key"),
        Index(
            "ix_care_actions_org_occurrence_acted", "organization_id", "occurrence_id", "acted_at"
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    occurrence_id: Mapped[UUID] = mapped_column(
        ForeignKey("care_reminder_occurrences.id"), index=True
    )
    lineage_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    series_id: Mapped[UUID] = mapped_column(ForeignKey("care_reminder_series.id"), index=True)
    occurrence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    acted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
