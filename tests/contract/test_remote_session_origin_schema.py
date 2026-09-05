from pathlib import Path

from services.api.app.persistence.models.identity import SessionRecord


def test_session_origin_model_is_indexed_and_constrained() -> None:
    table = SessionRecord.__table__
    assert table.c.session_origin.nullable is False
    assert table.c.session_origin.server_default is not None
    assert table.c.public_profile.nullable is True
    assert "ix_session_records_origin_status" in {index.name for index in table.indexes}
    constraints = " ".join(
        str(item.sqltext) for item in table.constraints if hasattr(item, "sqltext")
    )
    assert "remote_management_demo" in constraints
    assert "shared-demo-production" in constraints
    assert "shared-demo-dev" in constraints


def test_remote_session_origin_migration_is_single_head_and_reversible() -> None:
    source = Path("services/api/migrations/versions/0046_remote_session_origin.py").read_text()
    assert 'revision = "0046_remote_session_origin"' in source
    assert 'down_revision = "0045_remote_login_abuse"' in source
    assert 'server_default="legacy"' in source
    assert '"ix_session_records_origin_status"' in source
    assert 'op.drop_index("ix_session_records_origin_status"' in source
    assert 'op.drop_column("session_records", "public_profile")' in source
    assert 'op.drop_column("session_records", "session_origin")' in source
