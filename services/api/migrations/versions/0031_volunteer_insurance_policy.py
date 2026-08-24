"""Add the organization volunteer insurance requirement policy flag."""

import sqlalchemy as sa
from alembic import op

revision = "0031_volunteer_insurance_policy"
down_revision = "0030_volunteer_entry_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organization_volunteer_access_policies",
        sa.Column(
            "insurance_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("organization_volunteer_access_policies", "insurance_required")
