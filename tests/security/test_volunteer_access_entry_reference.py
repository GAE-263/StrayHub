from pathlib import Path

from services.api.app.domain.volunteer_access import (
    ENTRY_REFERENCE_PURPOSE,
    digest_entry_reference,
)


def test_entry_reference_digest_is_deterministic_and_raw_token_is_not_stored() -> None:
    raw = "entry-token-" + "a" * 64
    digest = digest_entry_reference(raw)
    assert len(digest) == 64
    assert digest == digest_entry_reference(raw)
    assert raw not in digest
    assert ENTRY_REFERENCE_PURPOSE == "volunteer_application_entry"


def test_entry_resolver_migration_uses_digest_purpose_and_minimal_output() -> None:
    migration = Path("services/api/migrations/versions/0024_volunteer_access_expand.py").read_text()
    assert "token_digest" in migration
    assert "purpose" in migration
    assert "reference_id" in migration
    assert "organization_id" in migration
    assert "REVOKE ALL" in migration
