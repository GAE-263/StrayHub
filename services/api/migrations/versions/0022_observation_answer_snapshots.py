"""Preserve observation display names used by historical reports."""

import sqlalchemy as sa
from alembic import op

revision = "0022_obs_answer_snapshots"
down_revision = "0021_us2_draft_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("care_reports", sa.Column("answer_snapshots", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("care_reports", "answer_snapshots")
