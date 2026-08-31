"""Adds AdoptionInquiry.adopter_name — the adopter's name, collected as part
of the "leave contact info" step (now name -> preferred contact time ->
phone number) alongside the existing phone_number column. Purely additive;
server_default keeps any existing row valid.
"""

import sqlalchemy as sa
from alembic import op

revision = "0043_adoption_inquiry_adopter_name"
down_revision = "0042_adoption_ai_followup_marker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "adoption_inquiries",
        sa.Column("adopter_name", sa.String(100), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("adoption_inquiries", "adopter_name")
