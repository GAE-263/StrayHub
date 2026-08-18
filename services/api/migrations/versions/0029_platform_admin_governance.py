"""Add the singleton platform administrator governance policy."""

import sqlalchemy as sa
from alembic import op

revision = "0029_platform_admin_governance"
down_revision = "0028_membership_archiving"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_admin_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("policy_key", sa.String(40), nullable=False),
        sa.Column("min_active_admins", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_active_admins", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("min_active_admins >= 1", name="ck_platform_admin_policy_min"),
        sa.CheckConstraint(
            "max_active_admins >= min_active_admins",
            name="ck_platform_admin_policy_bounds",
        ),
        sa.UniqueConstraint("policy_key", name="uq_platform_admin_policies_policy_key"),
    )
    op.execute(
        sa.text(
            "INSERT INTO platform_admin_policies "
            "(id, policy_key, min_active_admins, max_active_admins, version, "
            "created_at, updated_at) "
            "VALUES (gen_random_uuid(), 'default', 1, 2, 1, now(), now())"
        )
    )

    connection = op.get_bind()
    user_count = connection.execute(sa.text("SELECT count(*) FROM users")).scalar_one()
    active_admin_count = connection.execute(
        sa.text(
            "SELECT count(*) FROM users "
            "WHERE status = 'active' AND platform_role = 'PLATFORM_ADMIN'"
        )
    ).scalar_one()
    if user_count and not 1 <= active_admin_count <= 2:
        raise RuntimeError(
            "0029 platform admin governance requires 1-2 active PLATFORM_ADMIN users "
            "before serving traffic; repair existing users and rerun the migration"
        )


def downgrade() -> None:
    op.drop_table("platform_admin_policies")
