"""Opaque, revocable QR tokens."""

import sqlalchemy as sa
from alembic import op

revision = "0010_qr_codes"
down_revision = "0009_animals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "animal_qr_codes",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("organization_id", uuid, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("animal_id", uuid, sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_digest", name="uq_animal_qr_token_digest"),
    )
    op.create_index("ix_animal_qr_org_animal", "animal_qr_codes", ["organization_id", "animal_id"])
    op.execute("ALTER TABLE animal_qr_codes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE animal_qr_codes FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY animal_qr_codes_tenant_scope ON animal_qr_codes USING (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        ) WITH CHECK (
        current_setting('app.platform_scope', true) = 'true'
        OR organization_id::text = current_setting('app.current_org_id', true)
        )"""
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS animal_qr_codes_tenant_scope ON animal_qr_codes")
    op.drop_index("ix_animal_qr_org_animal", table_name="animal_qr_codes")
    op.drop_table("animal_qr_codes")
