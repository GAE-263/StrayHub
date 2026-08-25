"""Add one-time LIFF to LINE care-report handoffs."""

import sqlalchemy as sa
from alembic import op

revision = "0035_care_report_handoffs"
down_revision = "0034_volunteer_service_dates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "care_report_handoffs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "membership_id",
            uuid,
            sa.ForeignKey("organization_memberships.id"),
            nullable=False,
        ),
        sa.Column("animal_id", uuid, sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'consumed', 'expired', 'superseded')",
            name="ck_care_report_handoffs_status",
        ),
        sa.CheckConstraint(
            "source IN ('liff_scan', 'qr_deeplink', 'shelter_number')",
            name="ck_care_report_handoffs_source",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_care_report_handoffs_expiry",
        ),
    )
    op.create_index(
        "uq_care_report_handoffs_pending_user",
        "care_report_handoffs",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_care_report_handoffs_org_user_status",
        "care_report_handoffs",
        ["organization_id", "user_id", "status", "created_at"],
    )
    op.create_index(
        "ix_care_report_handoffs_pending_expiry",
        "care_report_handoffs",
        ["status", "expires_at", "organization_id"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.execute("ALTER TABLE care_report_handoffs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE care_report_handoffs FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY care_report_handoffs_tenant_scope
        ON care_report_handoffs
        USING (
          COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
          OR user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
        )
        WITH CHECK (
          COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
          OR user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
        )"""
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON care_report_handoffs TO strayhub_runtime")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS care_report_handoffs_tenant_scope ON care_report_handoffs")
    op.drop_table("care_report_handoffs")
