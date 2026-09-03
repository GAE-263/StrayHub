"""Pet growth diary (毛孩日記): adopters log periodic updates about an animal
they adopted through this system's own AdoptionInquiry record, visible to
shelter staff as a basis for post-adoption follow-up. Includes the AI
analysis output columns and the reminder-cadence clock in one migration
(the adoption branch split these across three revisions — see
0040_adoption_ai_suitability's docstring for that consolidation precedent).

RLS notes:

- `growth_diary_drafts` and `growth_diary_entries` both carry
  `adopter_user_id`, and both need an owner-or-tenant policy (not
  tenant-only): the LINE webhook must find "does this adopter have a
  pending draft / any past entries" *before* it knows which organization
  that draft/entry belongs to — the same "peek before scope is known"
  problem `adoption_drafts_owner_or_tenant` (0038_line_adoption) already
  solves for adoption_drafts, using `app.auth_user_id` via
  `set_authentication_user_scope`.
- `adoption_inquiries_tenant_scope` (0038_line_adoption) is replaced here
  with an owner-or-tenant policy for the same reason: 毛孩日記's history
  review (`list_inquiries_for_adopter`) is explicitly cross-shelter by that
  function's own docstring, but the tenant-only policy as it stood could
  only ever satisfy that under platform scope. This was latent/unexercised
  dead code before growth diary; nothing before this migration depended on
  the tenant-only behaviour.
"""

import sqlalchemy as sa
from alembic import op

revision = "0041_growth_diary"
down_revision = "0040_adoption_ai_suitability"
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
        # Populated asynchronously by a background Gemini analysis task (see
        # GrowthDiaryAiAnalysisService) — nullable/additive, may stay NULL
        # forever if no Gemini credentials are configured.
        sa.Column("ai_mood", sa.String(20)),
        sa.Column("ai_reply", sa.String(1000)),
        sa.Column("ai_staff_summary", sa.String(1000)),
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

    op.add_column(
        "adoption_inquiries",
        sa.Column("last_growth_diary_prompted_at", sa.DateTime(timezone=True), nullable=True),
    )

    for table in ("growth_diary_drafts", "growth_diary_entries"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""CREATE POLICY {table}_owner_or_tenant ON {table}
            USING (
              current_setting('app.platform_scope', true) = 'true'
              OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
              OR adopter_user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
            )
            WITH CHECK (
              current_setting('app.platform_scope', true) = 'true'
              OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
              OR adopter_user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
            )"""
        )

    op.execute("DROP POLICY IF EXISTS adoption_inquiries_tenant_scope ON adoption_inquiries")
    op.execute(
        """CREATE POLICY adoption_inquiries_owner_or_tenant ON adoption_inquiries
        USING (
          current_setting('app.platform_scope', true) = 'true'
          OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
          OR adopter_user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
        )
        WITH CHECK (
          current_setting('app.platform_scope', true) = 'true'
          OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
          OR adopter_user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
        )"""
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS adoption_inquiries_owner_or_tenant ON adoption_inquiries")
    op.execute(
        """CREATE POLICY adoption_inquiries_tenant_scope ON adoption_inquiries
        USING (organization_id::text = NULLIF(current_setting('app.current_org_id', true), ''))
        WITH CHECK (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )"""
    )
    op.drop_column("adoption_inquiries", "last_growth_diary_prompted_at")
    op.execute("DROP POLICY IF EXISTS growth_diary_entries_owner_or_tenant ON growth_diary_entries")
    op.execute("DROP POLICY IF EXISTS growth_diary_drafts_owner_or_tenant ON growth_diary_drafts")
    op.drop_table("growth_diary_entries")
    op.drop_table("growth_diary_drafts")
