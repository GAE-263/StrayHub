"""Organization-scoped animals and shelter numbers."""

import sqlalchemy as sa
from alembic import op

revision = "0009_animals"
down_revision = "0008_shelter_areas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "animals",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("shelter_number", sa.String(120)),
        sa.Column("current_photo_key", sa.String(500)),
        sa.Column("area_id", uuid, sa.ForeignKey("shelter_areas.id")),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "shelter_number", name="uq_animal_org_shelter_number"
        ),
    )
    op.create_index("ix_animals_org_status", "animals", ["organization_id", "status"])
    op.execute("ALTER TABLE animals ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE animals FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY animals_tenant_scope ON animals USING (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        ) WITH CHECK (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        )"""
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS animals_tenant_scope ON animals")
    op.drop_index("ix_animals_org_status", table_name="animals")
    op.drop_table("animals")
