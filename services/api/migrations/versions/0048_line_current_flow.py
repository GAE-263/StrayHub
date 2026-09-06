"""Persist the selected LINE conversation without changing tenant authorization."""

import sqlalchemy as sa
from alembic import op

revision = "0048_line_current_flow"
down_revision = "0047_report_review_summary"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("line_user_bindings", sa.Column("current_flow", sa.String(30), nullable=True))
    op.create_check_constraint(
        "ck_line_current_flow",
        "line_user_bindings",
        "current_flow IS NULL OR current_flow IN ('menu','care_report','adoption','growth_diary')",
    )


def downgrade():
    op.drop_constraint("ck_line_current_flow", "line_user_bindings", type_="check")
    op.drop_column("line_user_bindings", "current_flow")
