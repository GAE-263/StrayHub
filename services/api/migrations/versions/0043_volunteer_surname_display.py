"""Add non-encrypted volunteer surname for management-facing identification.

The full applicant name stays encrypted in volunteer_application_profiles under
its retention policy. Only the surname is copied out, so shelter staff can tell
two volunteers apart in care history without a PII reveal. Being outside the
encrypted store, this column is NOT covered by retention_expires_at /
pii_deleted_at purging.
"""

import sqlalchemy as sa
from alembic import op

revision = "0043_volunteer_surname_display"
down_revision = "0042_growth_diary_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "volunteer_applications",
        sa.Column("applicant_surname", sa.String(20), nullable=True),
    )
    op.add_column(
        "organization_memberships",
        sa.Column("volunteer_surname", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organization_memberships", "volunteer_surname")
    op.drop_column("volunteer_applications", "applicant_surname")
