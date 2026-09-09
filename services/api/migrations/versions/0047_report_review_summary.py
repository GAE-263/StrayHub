"""Care report summary projection and staff processing history (existing RLS)."""

import sqlalchemy as sa
from alembic import op

revision = "0047_report_review_summary"
down_revision = "0046_remote_session_origin"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("summary_data", sa.JSON(), nullable=True),
        sa.Column("summary_fingerprint", sa.String(64), nullable=True),
        sa.Column("summary_status", sa.String(30), nullable=False, server_default="not_requested"),
        sa.Column("attention_level", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("review_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("review_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_history", sa.JSON(), nullable=False, server_default="[]"),
    ):
        op.add_column("care_reports", column)
    op.create_check_constraint(
        "ck_report_review_status",
        "care_reports",
        "review_status IN ('pending','acknowledged','follow_up','resolved')",
    )
    # Historical reports receive deterministic flags only; no model calls/backfill.
    op.execute("""UPDATE care_reports SET attention_level = CASE
      WHEN answers->>'gait' = 'gait.abnormal' OR answers->>'defecation' = 'defecation.abnormal'
        OR answers->>'appearance_special_status' = 'appearance.wound' THEN 'urgent'
      WHEN answers->>'walk_completion' IN
        ('walk_completion.not_done','walk_completion.partially_completed')
        OR answers->>'activity' = 'activity.lower' OR answers->>'gait' = 'gait.off'
        OR answers->>'defecation' = 'defecation.soft'
        OR answers->>'animal_interaction' = 'animal_interaction.wary'
        OR answers->>'appearance_special_status' IN ('appearance.skin_or_coat','appearance.other')
      THEN 'review' ELSE 'normal' END""")
    op.create_index(
        "ix_report_inbox_review",
        "care_reports",
        ["organization_id", "review_status", "attention_level", "submitted_at"],
    )


def downgrade():
    op.drop_index("ix_report_inbox_review", table_name="care_reports")
    op.drop_constraint("ck_report_review_status", "care_reports", type_="check")
    for name in (
        "review_history",
        "review_version",
        "review_status",
        "attention_level",
        "summary_status",
        "summary_fingerprint",
        "summary_data",
    ):
        op.drop_column("care_reports", name)
