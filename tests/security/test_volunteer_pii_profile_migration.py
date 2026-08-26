from pathlib import Path

MIGRATION = Path("services/api/migrations/versions/0033_volunteer_pii_profile.py")


def test_pii_profile_migration_is_tenant_scoped_reversible_and_has_no_plaintext_columns() -> None:
    assert MIGRATION.exists()
    migration = MIGRATION.read_text()

    assert 'revision = "0033_volunteer_pii_profile"' in migration
    assert 'down_revision = "0032_public_volunteer_directory_scope"' in migration
    assert '"volunteer_application_profiles"' in migration
    assert "sa.LargeBinary(), nullable=True" in migration
    assert '"applicant_name_ciphertext"' in migration
    assert '"phone_ciphertext"' in migration
    assert '"basic_profile_ciphertext"' in migration
    assert '"insurance_identity_ciphertext"' in migration
    assert '"pii_schema_version"' in migration
    assert '"encryption_key_version"' in migration
    assert '"retention_expires_at"' in migration
    assert '"insurance_identity_delete_after"' in migration
    assert '"pii_deleted_at"' in migration
    assert 'applicant_name"' not in migration
    assert 'phone"' not in migration
    assert 'insurance_identity"' not in migration

    assert "uq_volunteer_applications_org_id" in migration
    assert "fk_volunteer_application_profiles_application_scope" in migration
    assert "ck_volunteer_application_profiles_deleted_payload" in migration
    assert "ck_volunteer_application_profiles_encryption_metadata" in migration
    assert "insurance_identity_delete_after <= created_at + interval '30 days'" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "volunteer_application_profiles_tenant_scope" in migration
    assert "current_setting('app.current_org_id', true)" in migration
    assert (
        "GRANT SELECT, INSERT, UPDATE, DELETE ON volunteer_application_profiles TO strayhub_runtime"
    ) in migration

    assert 'op.drop_table("volunteer_application_profiles")' in migration
    assert 'op.drop_constraint("uq_volunteer_applications_org_id"' in migration
