"""Add tenant-scoped encrypted volunteer application profiles."""

import sqlalchemy as sa
from alembic import op

revision = "0033_volunteer_pii_profile"
down_revision = "0032_public_volunteer_directory_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_volunteer_applications_org_id",
        "volunteer_applications",
        ["organization_id", "id"],
    )
    op.create_table(
        "volunteer_application_profiles",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("applicant_name_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("phone_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("basic_profile_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("insurance_identity_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("pii_schema_version", sa.String(length=20), nullable=False),
        sa.Column("encryption_algorithm", sa.String(length=30), nullable=False),
        sa.Column("encryption_key_version", sa.String(length=80), nullable=False),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("insurance_identity_delete_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pii_deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("application_id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["organization_id", "application_id"],
            ["volunteer_applications.organization_id", "volunteer_applications.id"],
            name="fk_volunteer_application_profiles_application_scope",
        ),
        sa.CheckConstraint(
            "(pii_deleted_at IS NULL AND applicant_name_ciphertext IS NOT NULL "
            "AND phone_ciphertext IS NOT NULL) OR "
            "(pii_deleted_at IS NOT NULL AND applicant_name_ciphertext IS NULL "
            "AND phone_ciphertext IS NULL AND basic_profile_ciphertext IS NULL "
            "AND insurance_identity_ciphertext IS NULL)",
            name="ck_volunteer_application_profiles_deleted_payload",
        ),
        sa.CheckConstraint(
            "(insurance_identity_ciphertext IS NULL "
            "AND insurance_identity_delete_after IS NULL) OR "
            "(pii_deleted_at IS NULL AND insurance_identity_ciphertext IS NOT NULL "
            "AND insurance_identity_delete_after IS NOT NULL "
            "AND insurance_identity_delete_after >= created_at "
            "AND insurance_identity_delete_after <= created_at + interval '30 days')",
            name="ck_volunteer_application_profiles_insurance_deadline",
        ),
        sa.CheckConstraint(
            "retention_expires_at > created_at",
            name="ck_volunteer_application_profiles_retention_future",
        ),
        sa.CheckConstraint(
            "length(trim(encryption_algorithm)) > 0 AND length(trim(encryption_key_version)) > 0",
            name="ck_volunteer_application_profiles_encryption_metadata",
        ),
    )
    op.create_index(
        "ix_volunteer_application_profiles_org_retention",
        "volunteer_application_profiles",
        ["organization_id", "retention_expires_at", "application_id"],
    )
    op.execute("ALTER TABLE volunteer_application_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE volunteer_application_profiles FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY volunteer_application_profiles_tenant_scope
        ON volunteer_application_profiles
        USING (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )
        WITH CHECK (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )"""
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON volunteer_application_profiles TO strayhub_runtime"
    )


def downgrade() -> None:
    op.drop_table("volunteer_application_profiles")
    op.drop_constraint("uq_volunteer_applications_org_id", "volunteer_applications")
