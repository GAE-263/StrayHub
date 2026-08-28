"""Pet growth diary: adopters log updates about an animal they adopted
through this system's own AdoptionInquiry record, visible to shelter staff
as a basis for post-adoption follow-up.

Both tables are always tenant-scoped (organization_id is never NULL here,
unlike adoption_drafts) — a diary entry can only exist once an
AdoptionInquiry has been submitted, which always has a real organization_id.
Standard RLS policy shape, safe to copy elsewhere.
"""

import sqlalchemy as sa
from alembic import op

revision = "0040_growth_diary"
down_revision = "0039_adoption_region_match"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)

    op.create_table(
        "growth_diary_drafts",
        sa.Column("adopter_user_id", uuid, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("inquiry_id", uuid, sa.ForeignKey("adoption_inquiries.id"), nullable=False),
        sa.Column("animal_id", uuid, sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_growth_diary_drafts_organization_id", "growth_diary_drafts", ["organization_id"]
    )

    op.create_table(
        "growth_diary_entries",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("inquiry_id", uuid, sa.ForeignKey("adoption_inquiries.id"), nullable=False),
        sa.Column("animal_id", uuid, sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("adopter_user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("photo_key", sa.String(500)),
        sa.Column("note", sa.String(2000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_growth_diary_entries_org_inquiry",
        "growth_diary_entries",
        ["organization_id", "inquiry_id"],
    )
    op.create_index("ix_growth_diary_entries_animal_id", "growth_diary_entries", ["animal_id"])
    op.create_index(
        "ix_growth_diary_entries_adopter_user_id", "growth_diary_entries", ["adopter_user_id"]
    )

    for table in ("growth_diary_drafts", "growth_diary_entries"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""CREATE POLICY {table}_tenant_scope ON {table} USING (
            current_setting('app.platform_scope', true) = 'true'
            OR organization_id::text = current_setting('app.current_org_id', true)
            ) WITH CHECK (
            current_setting('app.platform_scope', true) = 'true'
            OR organization_id::text = current_setting('app.current_org_id', true)
            )"""
        )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS growth_diary_entries_tenant_scope ON growth_diary_entries")
    op.execute("DROP POLICY IF EXISTS growth_diary_drafts_tenant_scope ON growth_diary_drafts")
    op.drop_table("growth_diary_entries")
    op.drop_table("growth_diary_drafts")
