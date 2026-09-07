"""加入收容所改成申請及管理員選角色審核。"""

import sqlalchemy as sa
from alembic import op

revision = "0051_join_applications"
down_revision = "0050_google_auth"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organization_join_applications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("organization_name", sa.String(200), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("role", sa.String(30)),
        sa.Column("reviewed_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('pending','approved','rejected')", name="ck_join_status"),
        sa.CheckConstraint(
            "role IS NULL OR role IN ('STAFF','SHELTER_ADMIN')", name="ck_join_role"
        ),
    )
    op.create_index("ix_join_user", "organization_join_applications", ["user_id"])
    op.create_index("ix_join_org", "organization_join_applications", ["organization_id"])
    op.create_index(
        "uq_join_pending",
        "organization_join_applications",
        ["organization_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.execute("""INSERT INTO organization_join_applications
      (id, created_at, updated_at, organization_id, organization_name, user_id, status)
      SELECT DISTINCT ON (organization_id, claimed_by)
        id, created_at, now(), organization_id, organization_name, claimed_by, 'pending'
      FROM organization_invitations
      WHERE status = 'claimed' AND claimed_by IS NOT NULL AND expires_at > now()
      ORDER BY organization_id, claimed_by, created_at DESC, id""")
    op.execute(
        "UPDATE organization_invitations SET status='revoked', updated_at=now() "
        "WHERE status IN ('open','claimed')"
    )
    op.execute("ALTER TABLE organization_join_applications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organization_join_applications FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY join_read ON organization_join_applications FOR SELECT USING (
      user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
      OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), ''))""")
    op.execute("""CREATE POLICY join_insert ON organization_join_applications
      FOR INSERT WITH CHECK (
      user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
      AND status='pending' AND role IS NULL AND reviewed_by IS NULL AND reviewed_at IS NULL)""")
    op.execute("""CREATE POLICY join_review ON organization_join_applications FOR UPDATE USING (
      organization_id::text = NULLIF(current_setting('app.current_org_id', true), ''))
      WITH CHECK (
        organization_id::text = NULLIF(current_setting('app.current_org_id', true), ''))""")
    # Exact lookup exposes only a name, never membership or other tenant fields.
    # Restore both settings before returning; an exception rolls back set_config.
    op.execute("""CREATE FUNCTION public.join_organization(target uuid)
      RETURNS TABLE(id uuid, name varchar) LANGUAGE plpgsql SECURITY DEFINER
      SET search_path = pg_catalog, public AS $$
      DECLARE previous_user text := current_setting('app.auth_user_id', true);
              previous_org text := current_setting('app.current_org_id', true);
      BEGIN
        IF NULLIF(previous_user, '') IS NULL THEN RETURN; END IF;
        PERFORM set_config('app.auth_user_id', '', true);
        PERFORM set_config('app.current_org_id', target::text, true);
        RETURN QUERY SELECT o.id, o.name FROM public.organizations o
          WHERE o.id=target AND o.status='active';
        PERFORM set_config('app.auth_user_id', COALESCE(previous_user,''), true);
        PERFORM set_config('app.current_org_id', COALESCE(previous_org,''), true);
      END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.join_organization(uuid) FROM PUBLIC")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='strayhub_runtime') THEN
      GRANT SELECT, INSERT, UPDATE ON organization_join_applications TO strayhub_runtime;
      REVOKE DELETE ON organization_join_applications FROM strayhub_runtime;
      GRANT EXECUTE ON FUNCTION public.join_organization(uuid) TO strayhub_runtime;
      END IF; END $$""")


def downgrade():
    op.execute("DROP FUNCTION public.join_organization(uuid)")
    op.drop_table("organization_join_applications")
