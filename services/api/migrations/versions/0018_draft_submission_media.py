"""Link submitted reports to drafts and draft media to formal reports."""

import sqlalchemy as sa
from alembic import op

revision = "0018_draft_submission_media"
down_revision = "0017_ai_job_claims"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.add_column(
        "care_reports",
        sa.Column("draft_id", uuid, sa.ForeignKey("care_report_drafts.id"), nullable=True),
    )
    op.create_index("ix_care_reports_draft_id", "care_reports", ["draft_id"], unique=True)
    op.create_foreign_key(
        "fk_draft_media_assets_media_asset_id",
        "draft_media_assets",
        "media_assets",
        ["media_asset_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_draft_media_assets_media_asset_id", "draft_media_assets", type_="foreignkey"
    )
    op.drop_index("ix_care_reports_draft_id", table_name="care_reports")
    op.drop_column("care_reports", "draft_id")
