"""Daily reportable animal scopes."""

import sqlalchemy as sa
from alembic import op

revision = "0011_reportable_scopes"
down_revision = "0010_qr_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "daily_reportable_scopes",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("animal_id", uuid, sa.ForeignKey("animals.id")),
        sa.Column("area_id", uuid, sa.ForeignKey("shelter_areas.id")),
        sa.Column("volunteer_user_id", uuid, sa.ForeignKey("users.id")),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "animal_id IS NOT NULL OR area_id IS NOT NULL",
            name="ck_reportable_scope_target",
        ),
    )
    op.create_index(
        "ix_reportable_scope_org_time",
        "daily_reportable_scopes",
        ["organization_id", "starts_at", "ends_at"],
    )
    op.execute("ALTER TABLE daily_reportable_scopes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE daily_reportable_scopes FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY reportable_scopes_tenant_scope ON daily_reportable_scopes USING (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        ) WITH CHECK (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        )"""
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS reportable_scopes_tenant_scope ON daily_reportable_scopes")
    op.drop_index("ix_reportable_scope_org_time", table_name="daily_reportable_scopes")
    op.drop_table("daily_reportable_scopes")
