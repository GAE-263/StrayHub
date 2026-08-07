"""Persistent AI job metadata and version traceability."""

import sqlalchemy as sa
from alembic import op

revision = "0007_ai_jobs"
down_revision = "0006_observation_vocabulary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "ai_processing_jobs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("job_type", sa.String(80), nullable=False),
        sa.Column("target_type", sa.String(80), nullable=False),
        sa.Column("target_id", uuid, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending_enqueue"),
        sa.Column("provider", sa.String(120), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("model_version", sa.String(200), nullable=False),
        sa.Column("prompt_template_id", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(120), nullable=False),
        sa.Column("output_schema_version", sa.String(120), nullable=False),
        sa.Column("raw_ai_output", sa.JSON),
        sa.Column("validation_result", sa.JSON),
        sa.Column("failure_reason", sa.String(500)),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "job_type",
            "target_type",
            "target_id",
            "model_version",
            "prompt_version",
            "output_schema_version",
            name="uq_ai_job_target_version",
        ),
    )
    op.create_index("ix_ai_jobs_org_status", "ai_processing_jobs", ["organization_id", "status"])
    op.execute("ALTER TABLE ai_processing_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_processing_jobs FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY ai_jobs_tenant_scope ON ai_processing_jobs USING (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        ) WITH CHECK (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        )"""
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ai_jobs_tenant_scope ON ai_processing_jobs")
    op.drop_index("ix_ai_jobs_org_status", table_name="ai_processing_jobs")
    op.drop_table("ai_processing_jobs")
