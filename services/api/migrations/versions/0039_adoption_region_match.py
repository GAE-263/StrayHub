"""Adoption UX rework support: organization region field, draft match results.

Purely additive — both columns are nullable/defaulted, so downgrade is a
plain column drop with no data-loss caveats beyond losing the new values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0039_adoption_region_match"
down_revision = "0038_adoption_matching"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("region", sa.String(20)))
    op.create_index("ix_organizations_region", "organizations", ["region"])

    op.add_column(
        "adoption_drafts",
        sa.Column("match_results", sa.JSON, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("adoption_drafts", "match_results")
    op.drop_index("ix_organizations_region", table_name="organizations")
    op.drop_column("organizations", "region")
