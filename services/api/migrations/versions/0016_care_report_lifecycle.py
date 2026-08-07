"""Care Report archive and correction history."""

import sqlalchemy as sa
from alembic import op

revision = "0016_care_report_lifecycle"
down_revision = "0015_ai_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.add_column("care_reports", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.add_column("care_reports", sa.Column("archived_by", uuid, sa.ForeignKey("users.id")))
    op.add_column("care_reports", sa.Column("archive_reason", sa.String(500)))
    op.create_table(
        "care_report_corrections",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("report_id", uuid, sa.ForeignKey("care_reports.id"), nullable=False),
        sa.Column("actor_user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("original_animal_id", uuid, sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("corrected_animal_id", uuid, sa.ForeignKey("animals.id")),
        sa.Column("before_data", sa.JSON, nullable=False),
        sa.Column("after_data", sa.JSON, nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_care_report_corrections_org_report",
        "care_report_corrections",
        ["organization_id", "report_id", "created_at"],
    )
    op.execute("ALTER TABLE care_report_corrections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE care_report_corrections FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY care_report_corrections_tenant_scope ON care_report_corrections USING (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        ) WITH CHECK (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        )"""
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS care_report_corrections_tenant_scope ON care_report_corrections"
    )
    op.drop_index("ix_care_report_corrections_org_report", table_name="care_report_corrections")
    op.drop_table("care_report_corrections")
    op.drop_column("care_reports", "archive_reason")
    op.drop_column("care_reports", "archived_by")
    op.drop_column("care_reports", "archived_at")
