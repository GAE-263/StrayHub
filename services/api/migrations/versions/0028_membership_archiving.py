"""Add organization Membership archiving metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0028_membership_archiving"
down_revision = "0027_medical_history_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organization_memberships",
        sa.Column("archived_from_status", sa.String(30), nullable=True),
    )
    op.add_column(
        "organization_memberships",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "organization_memberships",
        sa.Column(
            "archived_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("organization_memberships", "archived_by_user_id")
    op.drop_column("organization_memberships", "archived_at")
    op.drop_column("organization_memberships", "archived_from_status")
