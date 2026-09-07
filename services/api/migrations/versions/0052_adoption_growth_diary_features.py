"""Add adoption inbox metadata and concurrency-safe Growth Diary threads.

This revision is intentionally additive so the previous application release
can continue to run after the schema is deployed. Legacy ``photo_key`` data is
retained and mirrored into ``photo_keys``.
"""

import sqlalchemy as sa
from alembic import op

revision = "0052_adoption_growth_diary_features"
down_revision = "0051_join_applications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "adoption_drafts",
        sa.Column("freetext_profile_rounds", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "adoption_inquiries",
        sa.Column("ai_recommendation_overridden", sa.Boolean(), nullable=True),
    )

    op.add_column(
        "growth_diary_entries",
        sa.Column("photo_keys", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.execute(
        """
        UPDATE growth_diary_entries
        SET photo_keys = json_build_array(photo_key)
        WHERE photo_key IS NOT NULL
        """
    )
    op.add_column(
        "growth_diary_entries",
        sa.Column("entry_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
    )
    op.execute(
        """
        UPDATE growth_diary_entries
        SET entry_date = (created_at AT TIME ZONE 'UTC')::date
        """
    )
    op.add_column(
        "growth_diary_entries",
        sa.Column("content_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "growth_diary_entries",
        sa.Column("ai_content_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "growth_diary_entries",
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
    )
    op.add_column(
        "growth_diary_entries",
        sa.Column("status_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "growth_diary_entries",
        sa.Column(
            "status_updated_by_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_growth_diary_entries_entry_date", "growth_diary_entries", ["entry_date"]
    )
    op.create_index("ix_growth_diary_entries_status", "growth_diary_entries", ["status"])

    op.add_column(
        "growth_diary_drafts",
        sa.Column(
            "current_entry_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("growth_diary_entries.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "growth_diary_drafts", sa.Column("entry_date", sa.Date(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("growth_diary_drafts", "entry_date")
    op.drop_column("growth_diary_drafts", "current_entry_id")
    op.drop_index("ix_growth_diary_entries_status", table_name="growth_diary_entries")
    op.drop_index("ix_growth_diary_entries_entry_date", table_name="growth_diary_entries")
    op.drop_column("growth_diary_entries", "status_updated_by_user_id")
    op.drop_column("growth_diary_entries", "status_updated_at")
    op.drop_column("growth_diary_entries", "status")
    op.drop_column("growth_diary_entries", "ai_content_version")
    op.drop_column("growth_diary_entries", "content_version")
    op.drop_column("growth_diary_entries", "entry_date")
    op.drop_column("growth_diary_entries", "photo_keys")
    op.drop_column("adoption_inquiries", "ai_recommendation_overridden")
    op.drop_column("adoption_drafts", "freetext_profile_rounds")
