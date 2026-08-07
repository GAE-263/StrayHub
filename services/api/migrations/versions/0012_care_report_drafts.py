"""Server-side care report drafts."""

import sqlalchemy as sa
from alembic import op

revision = "0012_care_report_drafts"
down_revision = "0011_reportable_scopes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "care_report_drafts",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("opaque_token_digest", sa.String(64), nullable=False),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("volunteer_user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "membership_id", uuid, sa.ForeignKey("organization_memberships.id"), nullable=False
        ),
        sa.Column("animal_id", uuid, sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("current_step", sa.String(50), nullable=False, server_default="selecting_animal"),
        sa.Column("answers", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("note", sa.String(5000)),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("opaque_token_digest", name="uq_care_report_draft_token_digest"),
    )
    op.create_index(
        "ix_drafts_active_scope",
        "care_report_drafts",
        ["organization_id", "volunteer_user_id", "status"],
    )
    op.create_table(
        "draft_media_assets",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("draft_id", uuid, sa.ForeignKey("care_report_drafts.id"), nullable=False),
        sa.Column("media_asset_id", uuid, nullable=False),
        sa.Column("source_event_id", sa.String(128)),
    )
    op.execute("ALTER TABLE care_report_drafts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE care_report_drafts FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY care_report_drafts_tenant_scope ON care_report_drafts USING (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        ) WITH CHECK (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        )"""
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS care_report_drafts_tenant_scope ON care_report_drafts")
    op.drop_table("draft_media_assets")
    op.drop_index("ix_drafts_active_scope", table_name="care_report_drafts")
    op.drop_table("care_report_drafts")
