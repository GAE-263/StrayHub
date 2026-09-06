"""Free-text self-introduction intake for the questionnaire (方向 D — see
docs discussion) and AI-recommendation-override tracking:

- `adoption_drafts.freetext_profile_rounds` — how many AWAITING_FREETEXT_
  PROFILE rounds have been consumed (see AWAITING_FREETEXT_PROFILE_MAX_ROUNDS
  in domain.line_adoption_state), so the fallback to one-question-at-a-time
  survives a process restart mid-conversation same as everything else on
  this row.
- `adoption_inquiries.ai_recommendation_overridden` — 推薦名單 only: whether
  the adopter's final choice was outside the last AI-curated candidate list
  (see "browse_all_animals" in line_webhook.py) — raw signal for future
  matching-quality analysis, nothing currently reads it back.

Purely additive.
"""

import sqlalchemy as sa
from alembic import op

revision = "0042_adoption_freetext_profile"
down_revision = "0041_growth_diary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "adoption_drafts",
        sa.Column(
            "freetext_profile_rounds", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "adoption_inquiries",
        sa.Column("ai_recommendation_overridden", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("adoption_inquiries", "ai_recommendation_overridden")
    op.drop_column("adoption_drafts", "freetext_profile_rounds")
