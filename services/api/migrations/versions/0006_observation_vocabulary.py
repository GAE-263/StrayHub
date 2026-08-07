"""Observation category and option vocabulary."""

import sqlalchemy as sa
from alembic import op

revision = "0006_observation_vocabulary"
down_revision = "0005_audit_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "observation_categories",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id")),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "code", name="uq_observation_category_scope_code"),
    )
    op.create_table(
        "observation_options",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("category_id", uuid, sa.ForeignKey("observation_categories.id"), nullable=False),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id")),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("requires_note", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("category_id", "code", name="uq_observation_option_category_code"),
    )
    op.create_index(
        "ix_observation_options_org_status", "observation_options", ["organization_id", "status"]
    )
    for table in ("observation_categories", "observation_options"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""CREATE POLICY {table}_tenant_scope ON {table} USING (
            current_setting('app.platform_scope', true) = 'true'
            OR organization_id IS NULL
            OR organization_id::text = current_setting('app.current_org_id', true)
            ) WITH CHECK (
            current_setting('app.platform_scope', true) = 'true'
            OR organization_id IS NULL
            OR organization_id::text = current_setting('app.current_org_id', true)
            )"""
        )


def downgrade() -> None:
    for table in ("observation_options", "observation_categories"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_scope ON {table}")
    op.drop_index("ix_observation_options_org_status", table_name="observation_options")
    op.drop_table("observation_options")
    op.drop_table("observation_categories")
