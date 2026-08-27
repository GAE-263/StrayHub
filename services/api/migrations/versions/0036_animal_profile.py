"""Add nullable/default-safe animal profile fields; preserve tenant policies."""

import sqlalchemy as sa
from alembic import op

revision = "0036_animal_profile"
down_revision = "0035_care_report_handoffs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "animals", sa.Column("sex", sa.String(10), nullable=False, server_default="unknown")
    )
    op.add_column("animals", sa.Column("breed", sa.String(120), nullable=True))
    op.add_column("animals", sa.Column("intake_date", sa.Date(), nullable=True))
    op.add_column("animals", sa.Column("birth_date", sa.Date(), nullable=True))
    op.add_column(
        "animals",
        sa.Column("birth_date_estimated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("animals", sa.Column("age_description", sa.String(120), nullable=True))
    op.add_column("animals", sa.Column("behavior_notes", sa.Text(), nullable=True))
    op.add_column("animals", sa.Column("care_guidance", sa.Text(), nullable=True))
    op.create_check_constraint("ck_animals_sex", "animals", "sex IN ('male', 'female', 'unknown')")
    op.create_check_constraint("ck_animals_birth_intake", "animals", "birth_date <= intake_date")
    op.create_check_constraint(
        "ck_animals_estimated_birth",
        "animals",
        "NOT birth_date_estimated OR birth_date IS NOT NULL",
    )


def downgrade() -> None:
    for name in ("ck_animals_estimated_birth", "ck_animals_birth_intake", "ck_animals_sex"):
        op.drop_constraint(name, "animals", type_="check")
    for name in (
        "care_guidance",
        "behavior_notes",
        "age_description",
        "birth_date_estimated",
        "birth_date",
        "intake_date",
        "breed",
        "sex",
    ):
        op.drop_column("animals", name)
