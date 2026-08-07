"""Persist candidate animal and answer re-confirmation state for drafts."""

import sqlalchemy as sa
from alembic import op

revision = "0019_draft_reselection"
down_revision = "0018_draft_submission_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.add_column(
        "care_report_drafts",
        sa.Column("candidate_animal_id", uuid, sa.ForeignKey("animals.id"), nullable=True),
    )
    op.add_column(
        "care_report_drafts",
        sa.Column("reconfirmation_keys", sa.JSON, nullable=False, server_default="[]"),
    )
    op.create_index(
        "ix_care_report_drafts_candidate_animal_id",
        "care_report_drafts",
        ["candidate_animal_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_care_report_drafts_candidate_animal_id", table_name="care_report_drafts")
    op.drop_column("care_report_drafts", "reconfirmation_keys")
    op.drop_column("care_report_drafts", "candidate_animal_id")
