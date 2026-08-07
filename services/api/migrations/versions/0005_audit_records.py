"""Immutable audit record storage."""

import sqlalchemy as sa
from alembic import op

revision = "0005_audit_records"
down_revision = "0004_line_identity_and_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "audit_records",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id")),
        sa.Column("actor_user_id", uuid, sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", uuid),
        sa.Column("source_channel", sa.String(30), nullable=False),
        sa.Column("before_data", sa.JSON),
        sa.Column("after_data", sa.JSON),
        sa.Column("reason", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_audit_records_org_created", "audit_records", ["organization_id", "created_at"]
    )
    op.create_index("ix_audit_records_resource", "audit_records", ["resource_type", "resource_id"])
    op.execute("ALTER TABLE audit_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_records FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY audit_records_tenant_scope ON audit_records USING (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        ) WITH CHECK (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        )"""
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_records_tenant_scope ON audit_records")
    op.drop_index("ix_audit_records_resource", table_name="audit_records")
    op.drop_index("ix_audit_records_org_created", table_name="audit_records")
    op.drop_table("audit_records")
