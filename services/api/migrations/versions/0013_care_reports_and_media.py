"""Submitted care reports and private media."""

import sqlalchemy as sa
from alembic import op

revision = "0013_care_reports_and_media"
down_revision = "0012_care_report_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "media_assets",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="processed"),
        sa.Column("purpose", sa.String(80)),
        sa.Column("exif_removed", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("object_key", name="uq_media_asset_object_key"),
    )
    op.create_table(
        "care_reports",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("animal_id", uuid, sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("volunteer_user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "membership_id", uuid, sa.ForeignKey("organization_memberships.id"), nullable=False
        ),
        sa.Column("answers", sa.JSON, nullable=False),
        sa.Column("animal_name_snapshot", sa.String(200), nullable=False),
        sa.Column("shelter_number_snapshot", sa.String(120)),
        sa.Column("note", sa.String(5000)),
        sa.Column("status", sa.String(30), nullable=False, server_default="saved"),
        sa.Column("ai_job_status", sa.String(30), nullable=False, server_default="pending_enqueue"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_care_reports_org_animal_time",
        "care_reports",
        ["organization_id", "animal_id", "submitted_at"],
    )
    op.create_table(
        "care_report_media",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("report_id", uuid, sa.ForeignKey("care_reports.id"), nullable=False),
        sa.Column("media_asset_id", uuid, sa.ForeignKey("media_assets.id"), nullable=False),
    )
    op.create_table(
        "report_idempotency_keys",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("volunteer_user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("report_id", uuid, sa.ForeignKey("care_reports.id"), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "volunteer_user_id", "key", name="uq_report_idempotency_scope"
        ),
    )
    for table in ("media_assets", "care_reports", "report_idempotency_keys"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""CREATE POLICY {table}_tenant_scope ON {table} USING (
            current_setting('app.platform_scope', true) = 'true'
            OR organization_id::text = current_setting('app.current_org_id', true)
            ) WITH CHECK (
            current_setting('app.platform_scope', true) = 'true'
            OR organization_id::text = current_setting('app.current_org_id', true)
            )"""
        )


def downgrade() -> None:
    for table in ("report_idempotency_keys", "care_reports", "media_assets"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_scope ON {table}")
    op.drop_table("report_idempotency_keys")
    op.drop_table("care_report_media")
    op.drop_index("ix_care_reports_org_animal_time", table_name="care_reports")
    op.drop_table("care_reports")
    op.drop_table("media_assets")
