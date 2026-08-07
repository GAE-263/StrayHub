"""Indexes for Organization-scoped Animal Timeline queries."""

from alembic import op

revision = "0014_timeline_query_indexes"
down_revision = "0013_care_reports_and_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_care_reports_timeline_lookup",
        "care_reports",
        ["organization_id", "animal_id", "submitted_at", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_care_reports_timeline_lookup", table_name="care_reports")
