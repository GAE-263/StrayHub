"""Allow verified LINE actors to resolve only their own webhook context."""

from alembic import op

revision = "0056_line_webhook_auth_scope"
down_revision = "0055_expand_volunteer_profile_kms_key_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Membership effectiveness checks include an EXISTS against access grants.
    # Pre-tenant authentication may therefore read the verified user's grants,
    # but it still cannot insert or update them without organization scope.
    op.execute(
        "DROP POLICY IF EXISTS volunteer_access_grants_tenant_scope ON volunteer_access_grants"
    )
    op.execute(
        """CREATE POLICY volunteer_access_grants_tenant_scope
        ON volunteer_access_grants
        USING (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
          OR (
            NULLIF(current_setting('app.auth_user_id', true), '') IS NOT NULL
            AND user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
            AND (
              NULLIF(current_setting('app.auth_exact_org_id', true), '') IS NULL
              OR organization_id::text =
                NULLIF(current_setting('app.auth_exact_org_id', true), '')
            )
          )
        )
        WITH CHECK (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )"""
    )

    op.execute("DROP POLICY IF EXISTS webhook_sessions_tenant_scope ON webhook_sessions")
    op.execute(
        """CREATE POLICY webhook_sessions_tenant_scope
        ON webhook_sessions
        USING (
          COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR organization_id::text =
            NULLIF(current_setting('app.current_org_id', true), '')
          OR (
            NULLIF(current_setting('app.auth_user_id', true), '') IS NOT NULL
            AND user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
            AND (
              NULLIF(current_setting('app.auth_exact_org_id', true), '') IS NULL
              OR organization_id::text =
                NULLIF(current_setting('app.auth_exact_org_id', true), '')
            )
          )
        )
        WITH CHECK (
          COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR organization_id::text =
            NULLIF(current_setting('app.current_org_id', true), '')
          OR (
            NULLIF(current_setting('app.auth_user_id', true), '') IS NOT NULL
            AND NULLIF(current_setting('app.auth_exact_org_id', true), '') IS NOT NULL
            AND user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
            AND organization_id::text =
              NULLIF(current_setting('app.auth_exact_org_id', true), '')
          )
        )"""
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS webhook_sessions_tenant_scope ON webhook_sessions")
    op.execute(
        """CREATE POLICY webhook_sessions_tenant_scope ON webhook_sessions
        USING (
          current_setting('app.platform_scope', true) = 'true'
          OR organization_id::text = current_setting('app.current_org_id', true)
        )
        WITH CHECK (
          current_setting('app.platform_scope', true) = 'true'
          OR organization_id::text = current_setting('app.current_org_id', true)
        )"""
    )

    op.execute(
        "DROP POLICY IF EXISTS volunteer_access_grants_tenant_scope ON volunteer_access_grants"
    )
    op.execute(
        """CREATE POLICY volunteer_access_grants_tenant_scope
        ON volunteer_access_grants
        USING (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
          OR (
            user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
            AND organization_id::text =
              NULLIF(current_setting('app.auth_exact_org_id', true), '')
          )
        )
        WITH CHECK (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )"""
    )
