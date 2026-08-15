"""Allow named system actors for automated audit events.

Revision ID: 0026_audit_system_actor
Revises: 0025_volunteer_access_enforce
"""

from alembic import op

revision = "0026_audit_system_actor"
down_revision = "0025_volunteer_access_enforce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_audit_records_actor_identity", "audit_records", type_="check")
    op.create_check_constraint(
        "ck_audit_records_actor_identity",
        "audit_records",
        "(actor_type = 'user' AND actor_user_id IS NOT NULL AND actor_reference IS NULL) OR "
        "(actor_type = 'system' AND actor_user_id IS NULL AND actor_reference IS NOT NULL "
        "AND length(trim(actor_reference)) > 0)",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE audit_records SET actor_reference = 'SYSTEM_MIGRATION' "
        "WHERE actor_type = 'system' AND actor_reference <> 'SYSTEM_MIGRATION'"
    )
    op.drop_constraint("ck_audit_records_actor_identity", "audit_records", type_="check")
    op.create_check_constraint(
        "ck_audit_records_actor_identity",
        "audit_records",
        "(actor_type = 'user' AND actor_user_id IS NOT NULL AND actor_reference IS NULL) OR "
        "(actor_type = 'system' AND actor_user_id IS NULL "
        "AND actor_reference IN ('SYSTEM_MIGRATION'))",
    )
