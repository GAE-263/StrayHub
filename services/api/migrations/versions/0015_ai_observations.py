"""AI derived observations and call metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0015_ai_observations"
down_revision = "0014_timeline_query_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "ai_observations",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("job_id", uuid, sa.ForeignKey("ai_processing_jobs.id"), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_id", uuid),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("raw_ai_output", sa.JSON),
        sa.Column("validated_ai_observation", sa.JSON),
        sa.Column("human_review_result", sa.JSON),
        sa.Column("reviewed_by", uuid, sa.ForeignKey("users.id")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ai_observations_org_status",
        "ai_observations",
        ["organization_id", "status"],
    )
    op.create_table(
        "ai_call_logs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("job_id", uuid, sa.ForeignKey("ai_processing_jobs.id"), nullable=False),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("provider", sa.String(120), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("model_version", sa.String(200), nullable=False),
        sa.Column("prompt_version", sa.String(120), nullable=False),
        sa.Column("output_schema_version", sa.String(120), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for table in ("ai_observations", "ai_call_logs"):
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
    for table in ("ai_call_logs", "ai_observations"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_scope ON {table}")
    op.drop_table("ai_call_logs")
    op.drop_index("ix_ai_observations_org_status", table_name="ai_observations")
    op.drop_table("ai_observations")
