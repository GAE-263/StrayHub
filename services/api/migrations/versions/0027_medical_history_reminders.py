"""Medical history and care reminder foundations."""

import sqlalchemy as sa
from alembic import op

revision = "0027_medical_history_reminders"
down_revision = "0026_audit_system_actor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("timezone", sa.String(64), nullable=True))
    op.add_column("organizations", sa.Column("timezone_version", sa.Integer(), nullable=True))
    op.execute("UPDATE organizations SET timezone = 'Asia/Taipei' WHERE timezone IS NULL")
    op.execute("UPDATE organizations SET timezone_version = 1 WHERE timezone_version IS NULL")
    op.alter_column("organizations", "timezone", nullable=False, server_default="Asia/Taipei")
    op.alter_column("organizations", "timezone_version", nullable=False, server_default="1")
    op.add_column(
        "organization_memberships", sa.Column("medical_care_access", sa.Boolean(), nullable=True)
    )
    op.execute(
        "UPDATE organization_memberships SET medical_care_access = false "
        "WHERE medical_care_access IS NULL"
    )
    op.alter_column(
        "organization_memberships",
        "medical_care_access",
        nullable=False,
        server_default=sa.text("false"),
    )

    op.create_table(
        "medical_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("animal_id", sa.Uuid(), sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurred_timezone", sa.String(64), nullable=False, server_default="Asia/Taipei"),
        sa.Column("record_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("clinic", sa.String(300)),
        sa.Column("veterinarian", sa.String(200)),
        sa.Column("weight_kg", sa.Numeric(8, 3)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("archived_by_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("archive_reason", sa.Text()),
    )
    op.create_index(
        "ix_medical_records_org_animal_occurred",
        "medical_records",
        ["organization_id", "animal_id", "occurred_at"],
    )
    op.create_table(
        "medical_record_media",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column(
            "medical_record_id", sa.Uuid(), sa.ForeignKey("medical_records.id"), nullable=False
        ),
        sa.Column("media_asset_id", sa.Uuid(), sa.ForeignKey("media_assets.id"), nullable=False),
        sa.Column("attached_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("attached_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "medical_record_id", "media_asset_id"),
    )
    op.create_table(
        "care_reminder_series",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lineage_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("animal_id", sa.Uuid(), sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("reminder_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "assignee_membership_id", sa.Uuid(), sa.ForeignKey("organization_memberships.id")
        ),
        sa.Column("anchor_local_date", sa.Date(), nullable=False),
        sa.Column("anchor_local_time", sa.Time(), nullable=False),
        sa.Column("start_ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("end_ordinal", sa.Integer()),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("interval", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("end_local_date", sa.Date()),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("supersedes_series_id", sa.Uuid(), sa.ForeignKey("care_reminder_series.id")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True)),
        sa.Column("stopped_by_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("stop_reason", sa.Text()),
        sa.Column("suspended_at", sa.DateTime(timezone=True)),
        sa.Column("suspend_reason", sa.Text()),
    )
    op.create_index(
        "ix_care_series_org_status_animal",
        "care_reminder_series",
        ["organization_id", "status", "animal_id"],
    )
    op.create_table(
        "care_reminder_occurrences",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("lineage_id", sa.Uuid(), nullable=False),
        sa.Column("series_id", sa.Uuid(), sa.ForeignKey("care_reminder_series.id"), nullable=False),
        sa.Column("occurrence_index", sa.Integer(), nullable=False),
        sa.Column("nominal_local_date", sa.Date(), nullable=False),
        sa.Column("nominal_local_time", sa.Time(), nullable=False),
        sa.Column("original_scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_timezone", sa.String(64), nullable=False),
        sa.Column("timezone_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "assignee_membership_id", sa.Uuid(), sa.ForeignKey("organization_memberships.id")
        ),
        sa.Column("title_snapshot", sa.String(200), nullable=False),
        sa.Column("instructions_snapshot", sa.Text(), nullable=False, server_default=""),
        sa.Column("type_snapshot", sa.String(30), nullable=False),
        sa.Column("actual_completed_at", sa.DateTime(timezone=True)),
        sa.Column("recorded_at", sa.DateTime(timezone=True)),
        sa.Column("completed_by_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("result_note", sa.Text()),
        sa.Column("last_action_at", sa.DateTime(timezone=True)),
        sa.Column("last_action_by_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "lineage_id", "occurrence_index"),
    )
    op.create_index(
        "ix_care_occurrences_org_scheduled_status",
        "care_reminder_occurrences",
        ["organization_id", "scheduled_at", "status"],
    )
    op.create_table(
        "care_reminder_actions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column(
            "occurrence_id",
            sa.Uuid(),
            sa.ForeignKey("care_reminder_occurrences.id"),
            nullable=False,
        ),
        sa.Column("lineage_id", sa.Uuid(), nullable=False),
        sa.Column("series_id", sa.Uuid(), sa.ForeignKey("care_reminder_series.id"), nullable=False),
        sa.Column("occurrence_index", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(30), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("before_state", sa.JSON()),
        sa.Column("after_state", sa.JSON()),
        sa.Column("reason", sa.Text()),
        sa.Column("result_note", sa.Text()),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.UniqueConstraint("organization_id", "actor_user_id", "idempotency_key"),
    )
    for table in (
        "medical_records",
        "medical_record_media",
        "care_reminder_series",
        "care_reminder_occurrences",
        "care_reminder_actions",
    ):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO strayhub_runtime")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_scope ON {table}
            USING (
                COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
                OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
            )
            WITH CHECK (
                COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
                OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
            )
            """
        )


def downgrade() -> None:
    for table in (
        "care_reminder_actions",
        "care_reminder_occurrences",
        "care_reminder_series",
        "medical_record_media",
        "medical_records",
    ):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_scope ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
    op.drop_column("organization_memberships", "medical_care_access")
    op.drop_column("organizations", "timezone_version")
    op.drop_column("organizations", "timezone")
