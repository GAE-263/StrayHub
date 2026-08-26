"""Tenant-safe MOA animal source identity; no profile or lifecycle rewrite."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0037_animal_external_sources"
down_revision = "0036_animal_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_animals_org_id", "animals", ["organization_id", "id"])
    op.create_table(
        "animal_external_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("animal_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("external_id", sa.String(80), nullable=False),
        sa.Column("source_shelter_id", sa.String(40), nullable=False),
        sa.Column("source_updated_at", sa.Date(), nullable=True),
        sa.Column("last_imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_status", sa.String(20), nullable=False),
        sa.Column("source_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("photo_source_checksum", sa.String(64), nullable=True),
        sa.Column("photo_object_key", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "external_id", name="uq_animal_external_identity"),
        sa.UniqueConstraint("animal_id", "source", name="uq_animal_external_mapping"),
        sa.ForeignKeyConstraint(
            ["organization_id", "animal_id"],
            ["animals.organization_id", "animals.id"],
            name="fk_external_animal_tenant",
        ),
        sa.CheckConstraint("source = 'MOA_ADOPTION_OPEN_DATA'", name="ck_animal_external_source"),
        sa.CheckConstraint(
            "source_status IN ('present', 'unavailable')", name="ck_animal_external_status"
        ),
        sa.CheckConstraint(
            "octet_length(source_snapshot::text) <= 32768", name="ck_animal_external_snapshot_size"
        ),
    )
    op.create_index(
        "ix_animal_external_org_status",
        "animal_external_sources",
        ["organization_id", "source", "source_status"],
    )
    op.execute("ALTER TABLE animal_external_sources ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE animal_external_sources FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY animal_external_sources_tenant_scope ON animal_external_sources
        USING (COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), ''))
        WITH CHECK (COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), ''))""")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON animal_external_sources TO strayhub_runtime"
    )


def downgrade() -> None:
    op.drop_table("animal_external_sources")
    op.drop_constraint("uq_animals_org_id", "animals", type_="unique")
