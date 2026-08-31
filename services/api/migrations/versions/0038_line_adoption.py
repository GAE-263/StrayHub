"""Add the minimal tenant-safe LINE adoption schema.

This is a semantic consolidation of the adoption branch's 0038, 0039 and
0043 revisions. Growth Diary and optional AI columns are intentionally absent.
"""

import sqlalchemy as sa
from alembic import op

revision = "0038_line_adoption"
down_revision = "0037_animal_external_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)

    op.add_column("animals", sa.Column("species", sa.String(60)))
    op.add_column("animals", sa.Column("size", sa.String(30)))
    op.add_column("animals", sa.Column("energy", sa.String(30)))
    op.add_column("animals", sa.Column("temperament", sa.JSON))
    op.add_column(
        "animals",
        sa.Column("is_adoptable", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column("animals", sa.Column("adoption_notes", sa.String(2000)))
    op.create_index("ix_animals_org_adoptable", "animals", ["organization_id", "is_adoptable"])

    op.add_column("organizations", sa.Column("region", sa.String(20)))
    op.create_index("ix_organizations_region", "organizations", ["region"])

    op.create_table(
        "adoption_drafts",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("opaque_token_digest", sa.String(64), nullable=False),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id")),
        sa.Column("adopter_user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("path", sa.String(30)),
        sa.Column("target_animal_id", uuid, sa.ForeignKey("animals.id")),
        sa.Column("candidate_match_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("match_results", sa.JSON, nullable=False, server_default="[]"),
        sa.Column(
            "current_step", sa.String(50), nullable=False, server_default="selecting_organization"
        ),
        sa.Column("answers", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("reconfirmation_keys", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("opaque_token_digest", name="uq_adoption_draft_token_digest"),
    )
    op.create_index(
        "ix_adoption_drafts_active_scope",
        "adoption_drafts",
        ["organization_id", "adopter_user_id", "status"],
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_adoption_drafts_active_adopter "
        "ON adoption_drafts (adopter_user_id) WHERE status = 'active'"
    )

    op.create_table(
        "adoption_inquiries",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("draft_id", uuid, sa.ForeignKey("adoption_drafts.id"), nullable=False),
        sa.Column("adopter_user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("path", sa.String(30), nullable=False),
        sa.Column("target_animal_id", uuid, sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("animal_name_snapshot", sa.String(200), nullable=False),
        sa.Column("shelter_number_snapshot", sa.String(120)),
        sa.Column("answers", sa.JSON, nullable=False),
        sa.Column("match_scores_snapshot", sa.JSON),
        sa.Column("adopter_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("phone_number", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="new"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("staff_notes", sa.String(2000)),
        sa.Column("status_updated_at", sa.DateTime(timezone=True)),
        sa.Column("status_updated_by_user_id", uuid, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("draft_id", name="uq_adoption_inquiries_draft_id"),
    )
    op.create_index(
        "ix_adoption_inquiries_org_status",
        "adoption_inquiries",
        ["organization_id", "status", "submitted_at"],
    )

    op.execute("ALTER TABLE adoption_drafts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE adoption_drafts FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY adoption_drafts_owner_or_tenant ON adoption_drafts
        USING (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
          OR adopter_user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
        )
        WITH CHECK (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
          OR adopter_user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
        )"""
    )
    op.execute("ALTER TABLE adoption_inquiries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE adoption_inquiries FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY adoption_inquiries_tenant_scope ON adoption_inquiries
        USING (organization_id::text = NULLIF(current_setting('app.current_org_id', true), ''))
        WITH CHECK (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )"""
    )
    op.execute(
        """CREATE POLICY organizations_public_adoption_select ON organizations
        FOR SELECT USING (
          current_setting('app.public_adoption_directory', true) = 'true'
          AND status = 'active'
        )"""
    )
    op.execute(
        """CREATE POLICY animals_public_adoption_select ON animals
        FOR SELECT USING (
          current_setting('app.public_adoption_directory', true) = 'true'
          AND status = 'active'
          AND is_adoptable = true
        )"""
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS animals_public_adoption_select ON animals")
    op.execute("DROP POLICY IF EXISTS organizations_public_adoption_select ON organizations")
    op.execute("DROP POLICY IF EXISTS adoption_inquiries_tenant_scope ON adoption_inquiries")
    op.execute("DROP POLICY IF EXISTS adoption_drafts_owner_or_tenant ON adoption_drafts")
    op.drop_index("ix_adoption_inquiries_org_status", table_name="adoption_inquiries")
    op.drop_table("adoption_inquiries")
    op.execute("DROP INDEX IF EXISTS uq_adoption_drafts_active_adopter")
    op.drop_index("ix_adoption_drafts_active_scope", table_name="adoption_drafts")
    op.drop_table("adoption_drafts")
    op.drop_index("ix_organizations_region", table_name="organizations")
    op.drop_column("organizations", "region")
    op.drop_index("ix_animals_org_adoptable", table_name="animals")
    op.drop_column("animals", "adoption_notes")
    op.drop_column("animals", "is_adoptable")
    op.drop_column("animals", "temperament")
    op.drop_column("animals", "energy")
    op.drop_column("animals", "size")
    op.drop_column("animals", "species")
