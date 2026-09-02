from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from services.api.app.persistence.models.growth_diary import GrowthDiaryEntry

MIGRATION = Path("services/api/migrations/versions/0042_growth_diary_management.py")
EXPECTED_COLUMNS = {
    "photo_content_type",
    "ai_analysis_status",
    "ai_provider",
    "ai_model_name",
    "ai_model_version",
    "ai_prompt_version",
    "ai_output_schema_version",
    "ai_raw_output",
    "ai_analyzed_at",
}


def _load_migration() -> ModuleType:
    spec = spec_from_file_location("growth_diary_management_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_growth_diary_management_migration_has_single_head_chain() -> None:
    migration = _load_migration()

    assert migration.revision == "0042_growth_diary_management"
    assert migration.down_revision == "0041_growth_diary"


def test_upgrade_adds_only_the_nine_nullable_legacy_safe_columns(monkeypatch) -> None:
    migration = _load_migration()
    added: list[tuple[str, sa.Column]] = []
    executed: list[object] = []

    monkeypatch.setattr(
        migration.op, "add_column", lambda table, column: added.append((table, column))
    )
    monkeypatch.setattr(migration.op, "execute", executed.append)

    migration.upgrade()

    assert {column.name for _, column in added} == EXPECTED_COLUMNS
    assert len(added) == len(EXPECTED_COLUMNS)
    assert {table for table, _ in added} == {"growth_diary_entries"}
    assert all(column.nullable is True for _, column in added)
    assert executed == [], "legacy MIME and provenance must not be backfilled"

    by_name = {column.name: column for _, column in added}
    assert isinstance(by_name["ai_raw_output"].type, sa.JSON)
    assert isinstance(by_name["ai_analyzed_at"].type, sa.DateTime)
    assert by_name["ai_analyzed_at"].type.timezone is True


def test_downgrade_removes_only_the_nine_additive_columns(monkeypatch) -> None:
    migration = _load_migration()
    dropped: list[tuple[str, str]] = []

    monkeypatch.setattr(
        migration.op, "drop_column", lambda table, column: dropped.append((table, column))
    )

    migration.downgrade()

    assert {column for _, column in dropped} == EXPECTED_COLUMNS
    assert len(dropped) == len(EXPECTED_COLUMNS)
    assert {table for table, _ in dropped} == {"growth_diary_entries"}


def test_growth_diary_orm_matches_nullable_migration_columns() -> None:
    columns = GrowthDiaryEntry.__table__.columns

    assert EXPECTED_COLUMNS <= set(columns.keys())
    assert all(columns[name].nullable for name in EXPECTED_COLUMNS)
    assert isinstance(columns["ai_raw_output"].type, sa.JSON)
    assert isinstance(columns["ai_analyzed_at"].type, sa.DateTime)
    assert columns["ai_analyzed_at"].type.timezone is True
