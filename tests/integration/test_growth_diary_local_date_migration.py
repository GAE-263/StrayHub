import pathlib

MIGRATION = (
    pathlib.Path(__file__).resolve().parents[2]
    / "services/api/migrations/versions/0054_growth_diary_local_date_correction.py"
)


def test_growth_diary_local_date_correction_is_tenant_aware_and_downgrade_safe() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "0053_celery_ai_job_ledger"' in source
    assert "entry.organization_id" in source
    assert "organization.timezone" in source
    assert "pg_timezone_names" in source
    assert "ELSE 'UTC'" in source
    assert "IS DISTINCT FROM" in source
    assert "changes data semantics but adds no schema" in source
    assert "pass" in source
