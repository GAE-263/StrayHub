"""LINE bindings, webhook sessions and idempotent event metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0004_line_identity_and_events"
down_revision = "0003_tenant_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "line_user_bindings",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("line_user_id", sa.String(128), nullable=False),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("line_user_id", name="uq_line_user_bindings_line_user_id"),
    )
    op.create_index("ix_line_bindings_user", "line_user_bindings", ["user_id"])
    op.create_table(
        "webhook_sessions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_webhook_sessions_user_org", "webhook_sessions", ["user_id", "organization_id"]
    )
    op.create_table(
        "line_webhook_events",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("webhook_event_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("processing_status", sa.String(30), nullable=False, server_default="received"),
        sa.Column("redelivery", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(100)),
        sa.UniqueConstraint("webhook_event_id", name="uq_line_webhook_events_event_id"),
    )
    op.create_index("ix_line_webhook_events_status", "line_webhook_events", ["processing_status"])
    op.execute("ALTER TABLE webhook_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE webhook_sessions FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY webhook_sessions_tenant_scope ON webhook_sessions USING (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        ) WITH CHECK (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        )"""
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS webhook_sessions_tenant_scope ON webhook_sessions")
    op.drop_table("line_webhook_events")
    op.drop_index("ix_webhook_sessions_user_org", table_name="webhook_sessions")
    op.drop_table("webhook_sessions")
    op.drop_index("ix_line_bindings_user", table_name="line_user_bindings")
    op.drop_table("line_user_bindings")
