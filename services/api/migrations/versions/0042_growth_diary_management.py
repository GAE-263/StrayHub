"""Add private-photo metadata and AI provenance to Growth Diary entries.

The revision is deliberately additive and nullable. Existing entries do not
contain trustworthy photo MIME or historical AI invocation metadata, so no
backfill is attempted.
"""

import sqlalchemy as sa
from alembic import op

revision = "0042_growth_diary_management"
down_revision = "0041_growth_diary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "growth_diary_entries",
        sa.Column("photo_content_type", sa.String(100), nullable=True),
    )
    op.add_column(
        "growth_diary_entries",
        sa.Column("ai_analysis_status", sa.String(32), nullable=True),
    )
    op.add_column(
        "growth_diary_entries",
        sa.Column("ai_provider", sa.String(100), nullable=True),
    )
    op.add_column(
        "growth_diary_entries",
        sa.Column("ai_model_name", sa.String(200), nullable=True),
    )
    op.add_column(
        "growth_diary_entries",
        sa.Column("ai_model_version", sa.String(200), nullable=True),
    )
    op.add_column(
        "growth_diary_entries",
        sa.Column("ai_prompt_version", sa.String(100), nullable=True),
    )
    op.add_column(
        "growth_diary_entries",
        sa.Column("ai_output_schema_version", sa.String(100), nullable=True),
    )
    op.add_column(
        "growth_diary_entries",
        sa.Column("ai_raw_output", sa.JSON(), nullable=True),
    )
    op.add_column(
        "growth_diary_entries",
        sa.Column("ai_analyzed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("growth_diary_entries", "ai_analyzed_at")
    op.drop_column("growth_diary_entries", "ai_raw_output")
    op.drop_column("growth_diary_entries", "ai_output_schema_version")
    op.drop_column("growth_diary_entries", "ai_prompt_version")
    op.drop_column("growth_diary_entries", "ai_model_version")
    op.drop_column("growth_diary_entries", "ai_model_name")
    op.drop_column("growth_diary_entries", "ai_provider")
    op.drop_column("growth_diary_entries", "ai_analysis_status")
    op.drop_column("growth_diary_entries", "photo_content_type")
