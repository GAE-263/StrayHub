"""Add walk-report story and server-assigned media subject."""

import sqlalchemy as sa
from alembic import op

revision = "0039_walk_report_story_media"
down_revision = "0038_line_adoption"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media_assets", sa.Column("subject", sa.String(20), nullable=True))
    op.add_column("care_report_drafts", sa.Column("story", sa.String(2000), nullable=True))
    op.add_column("care_reports", sa.Column("story", sa.String(2000), nullable=True))


def downgrade() -> None:
    op.drop_column("care_reports", "story")
    op.drop_column("care_report_drafts", "story")
    op.drop_column("media_assets", "subject")
