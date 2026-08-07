"""Add worker claim and retry scheduling metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0017_ai_job_claims"
down_revision = "0016_care_report_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_processing_jobs",
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_processing_jobs",
        sa.Column("claim_token", sa.String(128), nullable=True),
    )
    op.add_column(
        "ai_processing_jobs",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_processing_jobs",
        sa.Column("claimed_by", sa.String(120), nullable=True),
    )
    op.create_index(
        "ix_ai_processing_jobs_claim_token",
        "ai_processing_jobs",
        ["claim_token"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_processing_jobs_claim_token", table_name="ai_processing_jobs")
    op.drop_column("ai_processing_jobs", "claimed_by")
    op.drop_column("ai_processing_jobs", "claimed_at")
    op.drop_column("ai_processing_jobs", "claim_token")
    op.drop_column("ai_processing_jobs", "available_at")
