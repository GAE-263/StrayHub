from pathlib import Path

from services.api.app.persistence.models.identity import (
    LoginAccountAbuseState,
    LoginIpAttempt,
)

ROOT = Path(__file__).resolve().parents[2]


def test_account_abuse_model_has_private_digest_state_and_constraint() -> None:
    table = LoginAccountAbuseState.__table__
    assert set(table.columns.keys()) >= {
        "id",
        "subject_digest",
        "consecutive_failures",
        "locked_until",
        "last_failed_at",
        "created_at",
        "updated_at",
    }
    assert "username" not in table.columns
    assert "password" not in table.columns
    assert table.columns.subject_digest.unique is True
    assert table.columns.locked_until.type.timezone is True
    assert table.columns.last_failed_at.type.timezone is True
    assert any(
        "consecutive_failures" in str(item.sqltext)
        for item in table.constraints
        if hasattr(item, "sqltext")
    )


def test_ip_attempt_model_has_rolling_window_index_without_raw_ip() -> None:
    table = LoginIpAttempt.__table__
    assert set(table.columns.keys()) >= {"id", "source_digest", "attempted_at"}
    assert "ip" not in table.columns
    assert table.columns.attempted_at.type.timezone is True
    assert any(
        [column.name for column in index.columns] == ["source_digest", "attempted_at"]
        for index in table.indexes
    )


def test_migration_creates_and_downgrades_both_tables() -> None:
    source = (ROOT / "services/api/migrations/versions/0045_remote_login_abuse.py").read_text()
    assert 'down_revision = "0044_volunteer_identity_history"' in source
    assert '"login_account_abuse_states"' in source
    assert '"login_ip_attempts"' in source
    assert 'op.drop_table("login_ip_attempts")' in source
    assert 'op.drop_table("login_account_abuse_states")' in source
