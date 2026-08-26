"""Bound volunteer entries and constrain LIFF authentication RLS scope."""

import sqlalchemy as sa
from alembic import op

revision = "0030_volunteer_entry_expiry"
down_revision = "0029_platform_admin_governance"
branch_labels = None
depends_on = None


def _replace_resolver(
    *, enforce_expiration: bool, include_public_context: bool, lock_authorization_rows: bool
) -> None:
    expiration_clause = "AND entry.expires_at > now()" if enforce_expiration else ""
    volatility = "VOLATILE" if lock_authorization_rows else "STABLE"
    lock_clause = "FOR UPDATE OF entry, organization" if lock_authorization_rows else ""
    if include_public_context:
        return_columns = (
            "reference_id uuid, organization_id uuid, "
            "organization_code varchar, organization_name varchar"
        )
        select_columns = "entry.id, entry.organization_id, organization.code, organization.name"
    else:
        return_columns = "reference_id uuid, organization_id uuid"
        select_columns = "entry.id, entry.organization_id"
    op.execute(
        "REVOKE ALL ON FUNCTION resolve_volunteer_entry_reference(text, text) FROM strayhub_runtime"
    )
    op.execute("DROP FUNCTION resolve_volunteer_entry_reference(text, text)")
    op.execute(
        f"""CREATE FUNCTION resolve_volunteer_entry_reference(
          p_token_digest text,
          p_purpose text DEFAULT 'volunteer_application_entry'
        ) RETURNS TABLE({return_columns})
        LANGUAGE sql
        SECURITY DEFINER
        {volatility}
        SET search_path = public, pg_temp
        AS $$
          SELECT {select_columns}
          FROM shelter_volunteer_entry_references AS entry
          JOIN organizations AS organization ON organization.id = entry.organization_id
          WHERE entry.token_digest = p_token_digest
            AND entry.purpose = p_purpose
            AND entry.status = 'active'
            {expiration_clause}
            AND organization.status = 'active'
          LIMIT 1
          {lock_clause}
        $$"""
    )
    op.execute("REVOKE ALL ON FUNCTION resolve_volunteer_entry_reference(text, text) FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION resolve_volunteer_entry_reference(text, text) "
        "TO strayhub_runtime"
    )


def _replace_authentication_policies() -> None:
    op.execute(
        "DROP POLICY IF EXISTS organization_memberships_tenant_scope ON organization_memberships"
    )
    op.execute("DROP POLICY IF EXISTS organizations_tenant_scope ON organizations")
    op.execute(
        """CREATE POLICY organization_memberships_tenant_scope ON organization_memberships
        USING (
          COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR (
            NULLIF(current_setting('app.auth_user_id', true), '') IS NOT NULL
            AND user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
            AND (
              NULLIF(current_setting('app.auth_exact_org_id', true), '') IS NOT NULL
              OR status = 'active'
            )
            AND (
              NULLIF(current_setting('app.auth_exact_org_id', true), '') IS NULL
              OR organization_id::text =
                NULLIF(current_setting('app.auth_exact_org_id', true), '')
            )
          )
          OR (
            NULLIF(current_setting('app.auth_user_id', true), '') IS NULL
            AND organization_id::text =
              NULLIF(current_setting('app.current_org_id', true), '')
          )
        )
        WITH CHECK (
          COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR (
            NULLIF(current_setting('app.auth_user_id', true), '') IS NULL
            AND organization_id::text =
              NULLIF(current_setting('app.current_org_id', true), '')
          )
        )"""
    )
    op.execute(
        """CREATE POLICY organizations_tenant_scope ON organizations
        USING (
          COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR (
            NULLIF(current_setting('app.auth_user_id', true), '') IS NULL
            AND id::text = NULLIF(current_setting('app.current_org_id', true), '')
          )
          OR (
            NULLIF(current_setting('app.auth_user_id', true), '') IS NOT NULL
            AND (
              NULLIF(current_setting('app.auth_exact_org_id', true), '') IS NULL
              OR id::text = NULLIF(current_setting('app.auth_exact_org_id', true), '')
            )
            AND EXISTS (
              SELECT 1
              FROM organization_memberships membership
              WHERE membership.organization_id = organizations.id
                AND membership.user_id::text =
                  NULLIF(current_setting('app.auth_user_id', true), '')
                AND membership.status = 'active'
            )
          )
        )
        WITH CHECK (
          COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR (
            NULLIF(current_setting('app.auth_user_id', true), '') IS NULL
            AND id::text = NULLIF(current_setting('app.current_org_id', true), '')
          )
        )"""
    )
    for table in ("volunteer_applications", "volunteer_access_grants"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_scope ON {table}")
        op.execute(
            f"""CREATE POLICY {table}_tenant_scope ON {table}
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


def _restore_previous_policies() -> None:
    op.execute(
        "DROP POLICY IF EXISTS organization_memberships_tenant_scope ON organization_memberships"
    )
    op.execute("DROP POLICY IF EXISTS organizations_tenant_scope ON organizations")
    op.execute(
        """CREATE POLICY organization_memberships_tenant_scope ON organization_memberships
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
        )"""
    )
    op.execute(
        """CREATE POLICY organizations_tenant_scope ON organizations
        USING (
          COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR id::text = NULLIF(current_setting('app.current_org_id', true), '')
          OR EXISTS (
            SELECT 1
            FROM organization_memberships membership
            WHERE membership.organization_id = organizations.id
              AND membership.user_id::text =
                NULLIF(current_setting('app.auth_user_id', true), '')
              AND membership.status = 'active'
          )
        )
        WITH CHECK (
          COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )"""
    )
    for table in ("volunteer_applications", "volunteer_access_grants"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_scope ON {table}")
        op.execute(
            f"""CREATE POLICY {table}_tenant_scope ON {table}
            USING (
              organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
            )
            WITH CHECK (
              organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
            )"""
        )


def upgrade() -> None:
    op.add_column(
        "shelter_volunteer_entry_references",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE shelter_volunteer_entry_references "
        "SET expires_at = issued_at + interval '90 days' WHERE expires_at IS NULL"
    )
    op.alter_column(
        "shelter_volunteer_entry_references",
        "expires_at",
        nullable=False,
        server_default=sa.text("now() + interval '90 days'"),
    )
    op.create_index(
        "ix_volunteer_entry_reference_expiry",
        "shelter_volunteer_entry_references",
        ["expires_at"],
    )
    _replace_resolver(
        enforce_expiration=True,
        include_public_context=True,
        lock_authorization_rows=True,
    )
    _replace_authentication_policies()


def downgrade() -> None:
    _restore_previous_policies()
    _replace_resolver(
        enforce_expiration=False,
        include_public_context=False,
        lock_authorization_rows=False,
    )
    op.drop_index(
        "ix_volunteer_entry_reference_expiry",
        table_name="shelter_volunteer_entry_references",
    )
    op.drop_column("shelter_volunteer_entry_references", "expires_at")
