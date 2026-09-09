"""Add shared PostgreSQL login abuse state."""

import sqlalchemy as sa
from alembic import op

revision = "0045_remote_login_abuse"
down_revision = "0044_volunteer_identity_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "login_account_abuse_states",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("subject_digest", sa.String(64), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "consecutive_failures >= 0 AND consecutive_failures <= 5",
            name="ck_login_account_abuse_failure_range",
        ),
        sa.UniqueConstraint("subject_digest", name="uq_login_account_abuse_subject"),
    )
    op.create_index(
        "ix_login_account_abuse_states_subject_digest",
        "login_account_abuse_states",
        ["subject_digest"],
        unique=True,
    )
    op.create_table(
        "login_ip_attempts",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_login_ip_attempt_source_time",
        "login_ip_attempts",
        ["source_digest", "attempted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_login_ip_attempt_source_time", table_name="login_ip_attempts")
    op.drop_table("login_ip_attempts")
    op.drop_index(
        "ix_login_account_abuse_states_subject_digest",
        table_name="login_account_abuse_states",
    )
    op.drop_table("login_account_abuse_states")
