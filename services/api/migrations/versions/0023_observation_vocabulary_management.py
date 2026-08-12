"""Add observation lifecycle, usage indexing, and audit operation grouping."""

import sqlalchemy as sa
from alembic import op

revision = "0023_obs_vocab_management"
down_revision = "0022_obs_answer_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_records",
        sa.Column(
            "operation_id",
            sa.Uuid(as_uuid=True),
            nullable=True,
            server_default=sa.text("md5(random()::text || clock_timestamp()::text)::uuid"),
        ),
    )
    op.add_column(
        "audit_records",
        sa.Column("result", sa.String(length=30), nullable=False, server_default="success"),
    )
    op.execute("UPDATE audit_records SET operation_id = id WHERE operation_id IS NULL")
    op.alter_column("audit_records", "operation_id", nullable=False)
    op.create_index("ix_audit_records_operation", "audit_records", ["operation_id"])

    op.create_check_constraint(
        "ck_observation_options_status",
        "observation_options",
        "status IN ('active', 'disabled', 'archived')",
    )
    op.create_table(
        "observation_option_usages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("care_report_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("observation_option_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("category_code", sa.String(length=80), nullable=False),
        sa.Column("option_code", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["care_report_id"], ["care_reports.id"]),
        sa.ForeignKeyConstraint(["observation_option_id"], ["observation_options.id"]),
        sa.UniqueConstraint(
            "organization_id",
            "care_report_id",
            "option_code",
            name="uq_observation_option_usage_report_code",
        ),
    )
    op.create_index(
        "ix_observation_option_usages_organization_id",
        "observation_option_usages",
        ["organization_id"],
    )
    op.create_index(
        "ix_observation_option_usages_care_report_id",
        "observation_option_usages",
        ["care_report_id"],
    )
    op.create_index(
        "ix_observation_option_usages_observation_option_id",
        "observation_option_usages",
        ["observation_option_id"],
    )
    op.create_index(
        "ix_observation_option_usage_org_code",
        "observation_option_usages",
        ["organization_id", "option_code"],
    )
    op.execute("ALTER TABLE observation_option_usages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE observation_option_usages FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY observation_option_usages_tenant_scope
        ON observation_option_usages USING (
          COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        ) WITH CHECK (
          COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )"""
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON observation_option_usages TO strayhub_runtime"
    )

    # Backfill only rows that have a JSON snapshot. The repeatable application
    # backfill handles legacy answer-only rows and can be rerun safely.
    op.execute(
        """INSERT INTO observation_option_usages
          (id, organization_id, care_report_id, observation_option_id,
           category_code, option_code, display_name, description, created_at)
        SELECT md5(cr.id::text || ':' || source.option_code)::uuid,
               cr.organization_id,
               cr.id,
               matched_option.id,
               COALESCE(source.category_code, split_part(source.option_code, '.', 1), source.field),
               source.option_code,
               source.display_name,
               source.description,
               COALESCE(cr.created_at, now())
        FROM care_reports cr
        CROSS JOIN LATERAL (
          SELECT answer_entry.key AS field,
                 COALESCE(
                   cr.answer_snapshots::jsonb -> answer_entry.key ->> 'code',
                   cr.answer_snapshots::jsonb -> answer_entry.key ->> 'stable_code',
                   CASE
                     WHEN jsonb_typeof(answer_entry.value) = 'string'
                     THEN answer_entry.value #>> '{}'
                   END
                 ) AS option_code,
                 cr.answer_snapshots::jsonb -> answer_entry.key ->> 'category_code'
                   AS category_code,
                 cr.answer_snapshots::jsonb -> answer_entry.key ->> 'display_name'
                   AS display_name,
                 cr.answer_snapshots::jsonb -> answer_entry.key ->> 'description'
                   AS description
          FROM jsonb_each(COALESCE(cr.answers::jsonb, '{}'::jsonb)) AS answer_entry
          UNION ALL
          SELECT snapshot_entry.key AS field,
                 COALESCE(
                   snapshot_entry.value ->> 'code',
                   snapshot_entry.value ->> 'stable_code'
                 ) AS option_code,
                 snapshot_entry.value ->> 'category_code' AS category_code,
                 snapshot_entry.value ->> 'display_name' AS display_name,
                 snapshot_entry.value ->> 'description' AS description
          FROM jsonb_each(COALESCE(cr.answer_snapshots::jsonb, '{}'::jsonb)) AS snapshot_entry
          WHERE NOT (cr.answers::jsonb ? snapshot_entry.key)
        ) AS source
        LEFT JOIN observation_options matched_option
          ON matched_option.code = source.option_code
         AND (
           matched_option.organization_id IS NULL
           OR matched_option.organization_id = cr.organization_id
         )
        WHERE source.option_code IS NOT NULL
        ON CONFLICT (organization_id, care_report_id, option_code) DO NOTHING"""
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS observation_option_usages_tenant_scope ON observation_option_usages"
    )
    op.execute("REVOKE ALL ON observation_option_usages FROM strayhub_runtime")
    op.drop_index("ix_observation_option_usage_org_code", table_name="observation_option_usages")
    op.drop_index(
        "ix_observation_option_usages_observation_option_id",
        table_name="observation_option_usages",
    )
    op.drop_index(
        "ix_observation_option_usages_care_report_id",
        table_name="observation_option_usages",
    )
    op.drop_index(
        "ix_observation_option_usages_organization_id",
        table_name="observation_option_usages",
    )
    op.drop_table("observation_option_usages")
    op.drop_constraint("ck_observation_options_status", "observation_options", type_="check")
    op.drop_index("ix_audit_records_operation", table_name="audit_records")
    op.drop_column("audit_records", "result")
    op.drop_column("audit_records", "operation_id")
