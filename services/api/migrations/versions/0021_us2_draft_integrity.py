"""Add US2 draft provenance metadata and enforce one active draft per volunteer."""

import sqlalchemy as sa
from alembic import op

revision = "0021_us2_draft_integrity"
down_revision = "0020_authentication_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "care_report_drafts",
        sa.Column(
            "answer_validation_version",
            sa.String(length=40),
            nullable=False,
            server_default="v1",
        ),
    )
    op.add_column(
        "care_report_drafts",
        sa.Column("answer_source_event_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "care_report_drafts",
        sa.Column("modification_summary", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index(
        "uq_care_report_drafts_active_volunteer",
        "care_report_drafts",
        ["organization_id", "volunteer_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_care_report_drafts_active_volunteer",
        table_name="care_report_drafts",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_column("care_report_drafts", "modification_summary")
    op.drop_column("care_report_drafts", "answer_source_event_id")
    op.drop_column("care_report_drafts", "answer_validation_version")
