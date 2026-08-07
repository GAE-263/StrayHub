"""Tenant RLS policy primitives."""

from alembic import op

revision = "0003_tenant_rls"
down_revision = "0002_identity_and_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The runtime role is deliberately not the migration role and can never bypass
    # RLS.  Keeping this role creation here makes an empty local database behave
    # like the deployed database while still leaving table ownership to the
    # migration principal.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'strayhub_runtime') THEN
                CREATE ROLE strayhub_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                    NOINHERIT NOREPLICATION NOBYPASSRLS;
            ELSE
                ALTER ROLE strayhub_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                    NOINHERIT NOREPLICATION NOBYPASSRLS;
            END IF;
        END $$;
        """
    )
    op.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA public TO strayhub_runtime")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO strayhub_runtime"
    )

    # The application sets these transaction-local values only after authenticating
    # the caller. FORCE prevents an accidentally privileged runtime role from
    # bypassing the policy; the migration role remains the only schema owner.
    for table in ("organizations", "organization_memberships"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO strayhub_runtime")
        scope_column = "id" if table == "organizations" else "organization_id"
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_scope ON {table}
            USING (
                COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
                OR {scope_column}::text = NULLIF(current_setting('app.current_org_id', true), '')
            )
            WITH CHECK (
                COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
                OR {scope_column}::text = NULLIF(current_setting('app.current_org_id', true), '')
            )
            """
        )


def downgrade() -> None:
    for table in ("organization_memberships", "organizations"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_scope ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM strayhub_runtime"
    )
    op.execute("REVOKE USAGE ON SCHEMA public FROM strayhub_runtime")
