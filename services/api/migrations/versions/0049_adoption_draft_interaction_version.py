"""Serialize and version LINE adoption draft interactions."""

import sqlalchemy as sa
from alembic import op

revision = "0049_adoption_draft_interaction_version"
down_revision = "0048_line_current_flow"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "adoption_drafts",
        sa.Column("interaction_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("adoption_drafts", "interaction_version")
