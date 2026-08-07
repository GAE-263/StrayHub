"""Tenant RLS policy primitives."""

from alembic import op

revision = "0003_tenant_rls"
down_revision = "0002_identity_and_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The application sets these transaction-local values only after authenticating
    # the caller.  FORCE prevents an accidentally privileged runtime role from
    # bypassing the policy; the migration role remains the only schema owner.
    for table in ("organizations", "organization_memberships"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        scope_column = "id" if table == "organizations" else "organization_id"
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_scope ON {table}
            USING (
                current_setting('app.platform_scope', true) = 'true'
                OR {scope_column}::text = current_setting('app.current_org_id', true)
            )
            WITH CHECK (
                current_setting('app.platform_scope', true) = 'true'
                OR {scope_column}::text = current_setting('app.current_org_id', true)
            )
            """
        )


def downgrade() -> None:
    for table in ("organization_memberships", "organizations"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_scope ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
