"""Track server-derived session origin for selective remote rollback."""

import sqlalchemy as sa
from alembic import op

revision = "0046_remote_session_origin"
down_revision = "0045_remote_login_abuse"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "session_records",
        sa.Column(
            "session_origin",
            sa.String(40),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.add_column(
        "session_records",
        sa.Column("public_profile", sa.String(40), nullable=True),
    )
    op.create_check_constraint(
        "ck_session_records_origin",
        "session_records",
        "session_origin IN ('legacy', 'local_web', 'liff', 'remote_management_demo')",
    )
    op.create_check_constraint(
        "ck_session_records_origin_profile",
        "session_records",
        "(session_origin = 'remote_management_demo' AND "
        "public_profile IN ('shared-demo-production', 'shared-demo-dev')) OR "
        "(session_origin IN ('legacy', 'local_web', 'liff') AND "
        "public_profile IS NULL)",
    )
    op.create_index(
        "ix_session_records_origin_status",
        "session_records",
        ["session_origin", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_session_records_origin_status", table_name="session_records")
    op.drop_constraint("ck_session_records_origin_profile", "session_records", type_="check")
    op.drop_constraint("ck_session_records_origin", "session_records", type_="check")
    op.drop_column("session_records", "public_profile")
    op.drop_column("session_records", "session_origin")
