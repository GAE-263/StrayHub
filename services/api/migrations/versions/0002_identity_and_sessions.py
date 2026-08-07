"""Identity, organization membership and session persistence."""

import sqlalchemy as sa
from alembic import op

revision = "0002_identity_and_sessions"
down_revision = "0001_bootstrap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "organizations",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("address", sa.String(500)),
        sa.Column("service_area", sa.String(200)),
        sa.Column("contact", sa.String(300)),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending_setup"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_organizations_code"),
    )
    op.create_index("ix_organizations_status", "organizations", ["status"])
    op.create_table(
        "users",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("username", sa.String(200), nullable=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(500), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("platform_role", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_status", "users", ["status"])
    op.create_table(
        "organization_memberships",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
    )
    op.create_index("ix_memberships_org", "organization_memberships", ["organization_id"])
    op.create_index("ix_memberships_user", "organization_memberships", ["user_id"])
    op.create_table(
        "session_records",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("active_organization_id", uuid, sa.ForeignKey("organizations.id")),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_user", "session_records", ["user_id"])
    op.create_table(
        "refresh_token_records",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("session_id", uuid, sa.ForeignKey("session_records.id"), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("family_id", uuid, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_digest", name="uq_refresh_token_digest"),
    )
    op.create_index("ix_refresh_token_session", "refresh_token_records", ["session_id"])


def downgrade() -> None:
    op.drop_table("refresh_token_records")
    op.drop_table("session_records")
    op.drop_table("organization_memberships")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_organizations_status", table_name="organizations")
    op.drop_table("organizations")
