from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "services/api/migrations/versions/0055_expand_volunteer_profile_kms_key_version.py"
)


def test_kms_key_version_migration_expands_storage_without_lossy_downgrade() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "0054_growth_diary_local_date_correction"' in source
    assert '"encryption_key_version"' in source
    assert "type_=sa.Text()" in source
    assert "length(encryption_key_version) > 80" in source
    assert "raise RuntimeError" in source
    assert "stored KMS resource names exceed 80 characters" in source
