"""Allow the public volunteer directory projection without widening writes."""

from alembic import op

revision = "0032_public_volunteer_directory_scope"
down_revision = "0031_volunteer_insurance_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DROP POLICY organization_volunteer_access_policies_tenant_scope "
        "ON organization_volunteer_access_policies"
    )
    op.execute(
        """CREATE POLICY organization_volunteer_access_policies_public_select
        ON organization_volunteer_access_policies
        FOR SELECT
        USING (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
          OR (
            current_setting('app.platform_scope', true) = 'true'
            AND current_setting('app.public_volunteer_directory', true) = 'true'
          )
        )"""
    )
    op.execute(
        """CREATE POLICY organization_volunteer_access_policies_tenant_insert
        ON organization_volunteer_access_policies
        FOR INSERT
        WITH CHECK (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )"""
    )
    op.execute(
        """CREATE POLICY organization_volunteer_access_policies_tenant_update
        ON organization_volunteer_access_policies
        FOR UPDATE
        USING (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )
        WITH CHECK (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )"""
    )
    op.execute(
        """CREATE POLICY organization_volunteer_access_policies_tenant_delete
        ON organization_volunteer_access_policies
        FOR DELETE
        USING (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )"""
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY organization_volunteer_access_policies_public_select "
        "ON organization_volunteer_access_policies"
    )
    op.execute(
        "DROP POLICY organization_volunteer_access_policies_tenant_insert "
        "ON organization_volunteer_access_policies"
    )
    op.execute(
        "DROP POLICY organization_volunteer_access_policies_tenant_update "
        "ON organization_volunteer_access_policies"
    )
    op.execute(
        "DROP POLICY organization_volunteer_access_policies_tenant_delete "
        "ON organization_volunteer_access_policies"
    )
    op.execute(
        """CREATE POLICY organization_volunteer_access_policies_tenant_scope
        ON organization_volunteer_access_policies
        USING (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )
        WITH CHECK (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )"""
    )
