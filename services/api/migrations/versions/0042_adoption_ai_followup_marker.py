"""Pending-marker column for the AI suitability follow-up question: non-NULL
means this draft is waiting for the adopter's free-text answer about special
requirements for the named animal, so the next non-phone-number text message
gets routed there instead of the usual "please enter your phone number"
rejection. Purely additive.
"""

import sqlalchemy as sa
from alembic import op

revision = "0042_adoption_ai_followup_marker"
down_revision = "0041_adoption_ai_suitability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "adoption_drafts",
        sa.Column(
            "ai_followup_target_animal_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("animals.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("adoption_drafts", "ai_followup_target_animal_id")
