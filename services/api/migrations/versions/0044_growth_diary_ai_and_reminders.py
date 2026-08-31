"""Growth diary AI analysis + periodic reminder cadence tracking:

- `growth_diary_entries.ai_mood` / `ai_reply` / `ai_staff_summary` — the two
  outputs of one Gemini analysis call (a warm reply for the adopter, an
  objective observation summary for shelter staff) plus the mood
  classification used to flag "concern" cases.
- `adoption_inquiries.last_growth_diary_prompted_at` — the reminder cadence
  clock (see services.api.app.domain.growth_diary_reminder).

Purely additive.
"""

import sqlalchemy as sa
from alembic import op

revision = "0044_growth_diary_ai_and_reminders"
down_revision = "0043_adoption_inquiry_adopter_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "growth_diary_entries", sa.Column("ai_mood", sa.String(20), nullable=True)
    )
    op.add_column(
        "growth_diary_entries", sa.Column("ai_reply", sa.String(1000), nullable=True)
    )
    op.add_column(
        "growth_diary_entries", sa.Column("ai_staff_summary", sa.String(1000), nullable=True)
    )
    op.add_column(
        "adoption_inquiries",
        sa.Column("last_growth_diary_prompted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("adoption_inquiries", "last_growth_diary_prompted_at")
    op.drop_column("growth_diary_entries", "ai_staff_summary")
    op.drop_column("growth_diary_entries", "ai_reply")
    op.drop_column("growth_diary_entries", "ai_mood")
