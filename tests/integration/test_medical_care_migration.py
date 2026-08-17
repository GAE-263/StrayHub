from pathlib import Path

MIGRATION = Path("services/api/migrations/versions/0027_medical_history_reminders.py")


def test_medical_migration_backfills_identity_fields_and_chains_from_previous_head() -> None:
    content = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0027_medical_history_reminders"' in content
    assert 'down_revision = "0026_audit_system_actor"' in content
    assert "Asia/Taipei" in content
    assert "timezone_version" in content
    assert "medical_care_access" in content


def test_all_new_tenant_tables_enable_and_force_rls() -> None:
    content = MIGRATION.read_text(encoding="utf-8")
    tables = (
        "medical_records",
        "medical_record_media",
        "care_reminder_series",
        "care_reminder_occurrences",
        "care_reminder_actions",
    )
    assert 'op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")' in content
    assert 'op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")' in content
    for table in tables:
        assert f'"{table}"' in content
