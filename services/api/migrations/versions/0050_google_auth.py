"""Google identity, browser transactions and tenant invitations."""

import sqlalchemy as sa
from alembic import op

revision = "0050_google_auth"
down_revision = "0049_adoption_draft_interaction_version"
branch_labels = None
depends_on = None


def _identity_columns():
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.add_column(
        "session_records",
        sa.Column("account_access_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_table(
        "google_user_bindings",
        *_identity_columns(),
        sa.Column("google_sub", sa.String(255), nullable=False, unique=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
    )
    op.create_table(
        "google_auth_transactions",
        *_identity_columns(),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("browser_digest", sa.String(64), nullable=False),
        sa.Column("csrf_digest", sa.String(64), nullable=False),
        sa.Column("nonce_digest", sa.String(64), nullable=False),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("session_records.id")),
        sa.Column("display_name", sa.String(200)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "ix_google_auth_transactions_expires_at", "google_auth_transactions", ["expires_at"]
    )
    op.create_table(
        "organization_invitations",
        *_identity_columns(),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("organization_name", sa.String(200), nullable=False),
        sa.Column("token_digest", sa.String(64), unique=True, nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("claimed_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('STAFF', 'SHELTER_ADMIN')", name="ck_invitation_role"),
        sa.CheckConstraint(
            "status IN ('open', 'claimed', 'approved', 'revoked')", name="ck_invitation_status"
        ),
    )
    for column in ("organization_id", "claimed_by"):
        op.create_index(
            f"ix_organization_invitations_{column}", "organization_invitations", [column]
        )
    op.execute("ALTER TABLE organization_invitations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organization_invitations FORCE ROW LEVEL SECURITY")
    # The exact digest scope is established only after authenticated, rate-limited
    # claim validation. No global organization discovery or tenant write scope.
    op.execute("""
        CREATE POLICY invitations_scope ON organization_invitations USING (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
          OR claimed_by::text = NULLIF(current_setting('app.auth_user_id', true), '')
          OR (token_digest = NULLIF(current_setting('app.invitation_digest', true), '')
              AND NULLIF(current_setting('app.auth_user_id', true), '') IS NOT NULL)
        ) WITH CHECK (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
          OR (token_digest = NULLIF(current_setting('app.invitation_digest', true), '')
              AND claimed_by::text = NULLIF(current_setting('app.auth_user_id', true), '')
              AND status = 'claimed')
        )
    """)
    # Append only: account events cannot read or alter tenant audit history.
    op.execute("""
        CREATE POLICY account_audit_insert ON audit_records FOR INSERT WITH CHECK (
          organization_id IS NULL AND resource_type = 'account'
          AND actor_user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
          AND resource_id = actor_user_id AND actor_type = 'user'
        )
    """)
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'strayhub_runtime') THEN
            GRANT SELECT, INSERT, UPDATE ON google_user_bindings, google_auth_transactions,
              organization_invitations TO strayhub_runtime;
            GRANT DELETE ON google_auth_transactions TO strayhub_runtime;
            REVOKE DELETE ON google_user_bindings, organization_invitations FROM strayhub_runtime;
          END IF;
        END $$
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS account_audit_insert ON audit_records")
    op.drop_table("organization_invitations")
    op.drop_table("google_auth_transactions")
    op.drop_table("google_user_bindings")
    op.drop_column("session_records", "account_access_enabled")
