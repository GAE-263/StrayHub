"""AI suitability analysis columns for the adoption-matching LINE bot —
consolidation of the adoption branch's 0041 and 0042 revisions (see
0038_line_adoption's docstring): nullable score/explanation columns on
adoption_drafts and adoption_inquiries, populated by a background Gemini
call keyed off entering AWAITING_AI_SUITABILITY on the 心有所屬 path, plus a
pending-marker column for that flow's low-score follow-up question. Purely
additive — no existing row/read path changes.
"""

import sqlalchemy as sa
from alembic import op

revision = "0040_adoption_ai_suitability"
down_revision = "0039_walk_report_story_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("adoption_drafts", sa.Column("ai_suitability_score", sa.Integer(), nullable=True))
    op.add_column(
        "adoption_drafts", sa.Column("ai_suitability_explanation", sa.String(2000), nullable=True)
    )
    op.add_column(
        "adoption_drafts",
        sa.Column(
            "ai_followup_target_animal_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("animals.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "adoption_inquiries", sa.Column("ai_suitability_score", sa.Integer(), nullable=True)
    )
    op.add_column(
        "adoption_inquiries",
        sa.Column("ai_suitability_explanation", sa.String(2000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("adoption_inquiries", "ai_suitability_explanation")
    op.drop_column("adoption_inquiries", "ai_suitability_score")
    op.drop_column("adoption_drafts", "ai_followup_target_animal_id")
    op.drop_column("adoption_drafts", "ai_suitability_explanation")
    op.drop_column("adoption_drafts", "ai_suitability_score")
