"""Store complete KMS CryptoKeyVersion resource names on volunteer profiles."""

import sqlalchemy as sa
from alembic import op

revision = "0055_expand_volunteer_profile_kms_key_version"
down_revision = "0054_growth_diary_local_date_correction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "volunteer_application_profiles",
        "encryption_key_version",
        existing_type=sa.String(length=80),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    connection = op.get_bind()
    oversized_values = connection.scalar(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM volunteer_application_profiles
                WHERE length(encryption_key_version) > 80
            )
            """
        )
    )
    if oversized_values:
        raise RuntimeError(
            "cannot downgrade volunteer profile encryption_key_version: "
            "stored KMS resource names exceed 80 characters"
        )
    op.alter_column(
        "volunteer_application_profiles",
        "encryption_key_version",
        existing_type=sa.Text(),
        type_=sa.String(length=80),
        existing_nullable=False,
    )
