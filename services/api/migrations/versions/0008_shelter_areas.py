"""Shelter areas and cages."""

import sqlalchemy as sa
from alembic import op

revision = "0008_shelter_areas"
down_revision = "0007_ai_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "shelter_areas",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("area_type", sa.String(40), nullable=False, server_default="area"),
        sa.Column("parent_id", uuid),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_shelter_area_org_name"),
    )
    op.create_index("ix_shelter_areas_org_status", "shelter_areas", ["organization_id", "status"])
    op.execute("ALTER TABLE shelter_areas ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE shelter_areas FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY shelter_areas_tenant_scope ON shelter_areas USING (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        ) WITH CHECK (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        )"""
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS shelter_areas_tenant_scope ON shelter_areas")
    op.drop_index("ix_shelter_areas_org_status", table_name="shelter_areas")
    op.drop_table("shelter_areas")
