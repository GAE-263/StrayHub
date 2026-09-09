"""Correct existing Growth Diary dates to each organization's local calendar date."""

import sqlalchemy as sa
from alembic import op

revision = "0054_growth_diary_local_date_correction"
down_revision = "0053_celery_ai_job_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE growth_diary_entries AS entry
            SET entry_date = (
                entry.created_at AT TIME ZONE CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM pg_timezone_names
                        WHERE name = organization.timezone
                    ) THEN organization.timezone
                    ELSE 'UTC'
                END
            )::date
            FROM organizations AS organization
            WHERE organization.id = entry.organization_id
              AND entry.entry_date IS DISTINCT FROM (
                  entry.created_at AT TIME ZONE CASE
                      WHEN EXISTS (
                          SELECT 1
                          FROM pg_timezone_names
                          WHERE name = organization.timezone
                      ) THEN organization.timezone
                      ELSE 'UTC'
                  END
              )::date
            """
        )
    )


def downgrade() -> None:
    # This revision changes data semantics but adds no schema. Keeping the
    # corrected dates is compatible with 0053; recreating the known-wrong UTC
    # values would be both lossy and unsafe.
    pass
