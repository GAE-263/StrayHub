"""Permit pre-context authentication to inspect only the authenticated user's scope."""

from alembic import op

revision = "0020_authentication_scope"
down_revision = "0019_draft_reselection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS organization_memberships_tenant_scope ON organization_memberships"
    )
    op.execute("DROP POLICY IF EXISTS organizations_tenant_scope ON organizations")
    op.execute(
        """
        CREATE POLICY organization_memberships_tenant_scope ON organization_memberships
        USING (
            COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
            OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
            OR (
                user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
                AND status = 'active'
            )
        )
        WITH CHECK (
            COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
            OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )
        """
    )
    op.execute(
        """
        CREATE POLICY organizations_tenant_scope ON organizations
        USING (
            COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
            OR id::text = NULLIF(current_setting('app.current_org_id', true), '')
            OR EXISTS (
                SELECT 1
                FROM organization_memberships membership
                WHERE membership.organization_id = organizations.id
                  AND membership.user_id::text = NULLIF(
                      current_setting('app.auth_user_id', true), ''
                  )
                  AND membership.status = 'active'
            )
        )
        WITH CHECK (
            COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
            OR id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS organization_memberships_tenant_scope ON organization_memberships"
    )
    op.execute("DROP POLICY IF EXISTS organizations_tenant_scope ON organizations")
    op.execute(
        """
        CREATE POLICY organization_memberships_tenant_scope ON organization_memberships
        USING (
            COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
            OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )
        WITH CHECK (
            COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
            OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )
        """
    )
    op.execute(
        """
        CREATE POLICY organizations_tenant_scope ON organizations
        USING (
            COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
            OR id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )
        WITH CHECK (
            COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
            OR id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )
        """
    )
