"""Scaffolding for the (not-yet-wired) AI suitability analysis feature:
nullable score/explanation columns on adoption_drafts and adoption_inquiries,
populated later by a background Gemini call keyed off entering
AWAITING_PHONE_NUMBER on the 心有所屬 path. Purely additive — no existing
row/read path changes until that trigger is implemented.
"""

import sqlalchemy as sa
from alembic import op

revision = "0041_adoption_ai_suitability"
down_revision = "0040_growth_diary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("adoption_drafts", sa.Column("ai_suitability_score", sa.Integer(), nullable=True))
    op.add_column(
        "adoption_drafts", sa.Column("ai_suitability_explanation", sa.String(2000), nullable=True)
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
    op.drop_column("adoption_drafts", "ai_suitability_explanation")
    op.drop_column("adoption_drafts", "ai_suitability_score")
