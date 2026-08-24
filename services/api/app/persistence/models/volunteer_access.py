"""Tenant-scoped CRM models for volunteer applications and finite access."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from services.api.app.persistence.database.base import AuditMixin, Base, IdentityMixin, utc_now


class OrganizationVolunteerAccessPolicy(AuditMixin, Base):
    __tablename__ = "organization_volunteer_access_policies"
    __table_args__ = (
        CheckConstraint(
            "default_grant_duration_hours > 0",
            name="ck_volunteer_access_policy_positive_duration",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    applications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    insurance_required: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    default_grant_duration_hours: Mapped[int] = mapped_column(
        Integer, default=168, server_default=text("168"), nullable=False
    )
    daily_application_limit: Mapped[int] = mapped_column(
        Integer, default=20, server_default=text("20"), nullable=False
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )


class ShelterVolunteerEntryReference(IdentityMixin, AuditMixin, Base):
    __tablename__ = "shelter_volunteer_entry_references"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'revoked')", name="ck_volunteer_entry_reference_status"
        ),
        CheckConstraint(
            "(issued_by_user_id IS NOT NULL) <> (issued_by_actor_reference IS NOT NULL)",
            name="ck_volunteer_entry_reference_issue_actor",
        ),
        CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL "
            "AND revoked_by_user_id IS NULL AND revoked_by_actor_reference IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL "
            "AND ((revoked_by_user_id IS NOT NULL) <> "
            "(revoked_by_actor_reference IS NOT NULL)))",
            name="ck_volunteer_entry_reference_revoke_fields",
        ),
        Index(
            "ix_volunteer_entry_reference_org_status_issued",
            "organization_id",
            "status",
            "issued_at",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    purpose: Mapped[str] = mapped_column(String(80), default="volunteer_application_entry")
    status: Mapped[str] = mapped_column(String(20), default="active")
    issued_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    issued_by_actor_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now() + interval '90 days'"),
        nullable=False,
    )
    revoked_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_by_actor_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotation_group_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), default=uuid4, index=True)


class VolunteerApplication(IdentityMixin, AuditMixin, Base):
    __tablename__ = "volunteer_applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'withdrawn')",
            name="ck_volunteer_applications_status",
        ),
        CheckConstraint(
            "(status NOT IN ('approved', 'rejected') OR decided_at IS NOT NULL) "
            "AND (status <> 'rejected' OR "
            "(decision_reason IS NOT NULL AND length(trim(decision_reason)) > 0)) "
            "AND (status <> 'withdrawn' OR withdrawn_at IS NOT NULL)",
            name="ck_volunteer_applications_terminal_fields",
        ),
        Index(
            "uq_volunteer_applications_pending_user_org",
            "organization_id",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "uq_volunteer_applications_client_request",
            "organization_id",
            "user_id",
            "client_request_id",
            unique=True,
            postgresql_where=text("client_request_id IS NOT NULL"),
        ),
        Index(
            "ix_volunteer_applications_org_status_submitted",
            "organization_id",
            "status",
            "submitted_at",
            "id",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_volunteer_applications_org_id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    source_channel: Mapped[str] = mapped_column(String(30), default="liff")
    client_request_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    previous_application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("volunteer_applications.id"), nullable=True
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )


class VolunteerApplicationServiceDate(IdentityMixin, AuditMixin, Base):
    """One independently reviewable service-date request for an application."""

    __tablename__ = "volunteer_application_service_dates"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "application_id",
            "service_date",
            name="uq_volunteer_application_service_date",
        ),
        Index(
            "ix_volunteer_service_dates_org_date_status",
            "organization_id",
            "service_date",
            "status",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'withdrawn')",
            name="ck_volunteer_service_date_status",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("volunteer_applications.id"))
    service_date: Mapped[date] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )


class VolunteerApplicationProfile(AuditMixin, Base):
    __tablename__ = "volunteer_application_profiles"
    __table_args__ = (
        CheckConstraint(
            "(pii_deleted_at IS NULL AND applicant_name_ciphertext IS NOT NULL "
            "AND phone_ciphertext IS NOT NULL) OR "
            "(pii_deleted_at IS NOT NULL AND applicant_name_ciphertext IS NULL "
            "AND phone_ciphertext IS NULL AND basic_profile_ciphertext IS NULL "
            "AND insurance_identity_ciphertext IS NULL)",
            name="ck_volunteer_application_profiles_deleted_payload",
        ),
        CheckConstraint(
            "(insurance_identity_ciphertext IS NULL "
            "AND insurance_identity_delete_after IS NULL) OR "
            "(pii_deleted_at IS NULL AND insurance_identity_ciphertext IS NOT NULL "
            "AND insurance_identity_delete_after IS NOT NULL "
            "AND insurance_identity_delete_after >= created_at "
            "AND insurance_identity_delete_after <= created_at + interval '30 days')",
            name="ck_volunteer_application_profiles_insurance_deadline",
        ),
        CheckConstraint(
            "retention_expires_at > created_at",
            name="ck_volunteer_application_profiles_retention_future",
        ),
        CheckConstraint(
            "length(trim(encryption_algorithm)) > 0 AND length(trim(encryption_key_version)) > 0",
            name="ck_volunteer_application_profiles_encryption_metadata",
        ),
        Index(
            "ix_volunteer_application_profiles_org_retention",
            "organization_id",
            "retention_expires_at",
            "application_id",
        ),
        ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["volunteer_applications.organization_id", "volunteer_applications.id"],
            name="fk_volunteer_application_profiles_application_scope",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    applicant_name_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    phone_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    basic_profile_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    insurance_identity_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    pii_schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    encryption_algorithm: Mapped[str] = mapped_column(String(30), nullable=False)
    encryption_key_version: Mapped[str] = mapped_column(String(80), nullable=False)
    retention_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    insurance_identity_delete_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pii_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VolunteerAccessGrant(IdentityMixin, AuditMixin, Base):
    __tablename__ = "volunteer_access_grants"
    __table_args__ = (
        UniqueConstraint("application_id", name="uq_volunteer_access_grants_application"),
        CheckConstraint("expires_at > valid_from", name="ck_volunteer_access_grants_period"),
        CheckConstraint(
            "status IN ('active', 'expired', 'revoked')",
            name="ck_volunteer_access_grants_status",
        ),
        CheckConstraint(
            "(status <> 'revoked') OR (revoked_at IS NOT NULL "
            "AND revoked_by_user_id IS NOT NULL AND revocation_reason IS NOT NULL "
            "AND length(trim(revocation_reason)) > 0)",
            name="ck_volunteer_access_grants_revocation_fields",
        ),
        Index(
            "uq_volunteer_access_grants_active_membership",
            "membership_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "ix_volunteer_access_grants_due",
            "status",
            "expires_at",
            "organization_id",
            postgresql_where=text("status = 'active'"),
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    membership_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization_memberships.id"), index=True
    )
    application_id: Mapped[UUID] = mapped_column(ForeignKey("volunteer_applications.id"))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    policy_version_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_hours_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_type: Mapped[str] = mapped_column(String(30), default="manager_approval")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )


class VolunteerDecisionBatch(IdentityMixin, AuditMixin, Base):
    __tablename__ = "volunteer_decision_batches"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "operation_id", name="uq_volunteer_decision_batches_operation"
        ),
        CheckConstraint("requested_count > 0", name="ck_volunteer_decision_batches_requested"),
        CheckConstraint(
            "processed_count = succeeded_count + conflict_count + failed_count",
            name="ck_volunteer_decision_batches_counts",
        ),
        Index("ix_volunteer_decision_batches_org_actor", "organization_id", "actor_user_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    actor_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    platform_support_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decision: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    default_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    policy_version_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_duration_hours_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selection_mode: Mapped[str] = mapped_column(String(30))
    filter_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    requested_count: Mapped[int] = mapped_column(Integer)
    processed_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    succeeded_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    conflict_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    failed_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VolunteerDecisionBatchItem(IdentityMixin, AuditMixin, Base):
    __tablename__ = "volunteer_decision_batch_items"
    __table_args__ = (
        UniqueConstraint(
            "batch_id", "application_id", name="uq_volunteer_decision_batch_items_target"
        ),
        Index(
            "ix_volunteer_decision_batch_items_claim",
            "organization_id",
            "batch_id",
            "result",
            "id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    batch_id: Mapped[UUID] = mapped_column(ForeignKey("volunteer_decision_batches.id"))
    application_id: Mapped[UUID] = mapped_column(ForeignKey("volunteer_applications.id"))
    expected_version: Mapped[int] = mapped_column(Integer)
    override_valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    override_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    claim_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resulting_application_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    membership_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organization_memberships.id"), nullable=True
    )
    grant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("volunteer_access_grants.id"), nullable=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VolunteerNotificationDelivery(IdentityMixin, AuditMixin, Base):
    __tablename__ = "volunteer_notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_volunteer_notifications_event"
        ),
        CheckConstraint("attempt_count >= 0", name="ck_volunteer_notifications_attempt_count"),
        Index("ix_volunteer_notifications_claim", "status", "available_at", "organization_id"),
        Index(
            "ix_volunteer_notifications_failure_list",
            "organization_id",
            "status",
            "last_failed_at",
            "id",
            postgresql_where=text("status IN ('retry_wait', 'failed')"),
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    line_binding_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("line_user_bindings.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(50))
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    idempotency_key: Mapped[str] = mapped_column(String(160))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    claim_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VolunteerNotificationRetryBatch(IdentityMixin, AuditMixin, Base):
    __tablename__ = "volunteer_notification_retry_batches"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "operation_id",
            name="uq_volunteer_notification_retry_batches_operation",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    actor_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    platform_support_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    requested_count: Mapped[int] = mapped_column(Integer)
    requeued_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    conflict_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))


class VolunteerNotificationRetryBatchItem(IdentityMixin, AuditMixin, Base):
    __tablename__ = "volunteer_notification_retry_batch_items"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "notification_delivery_id",
            name="uq_volunteer_notification_retry_items_target",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    batch_id: Mapped[UUID] = mapped_column(ForeignKey("volunteer_notification_retry_batches.id"))
    notification_delivery_id: Mapped[UUID] = mapped_column(
        ForeignKey("volunteer_notification_deliveries.id")
    )
    result: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
