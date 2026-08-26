from pathlib import Path

from services.api.app.persistence.models.volunteer_access import (
    ShelterVolunteerEntryReference,
)


def test_volunteer_entry_reference_has_expiration_and_resolver_enforces_it() -> None:
    assert "expires_at" in ShelterVolunteerEntryReference.__table__.columns
    migration = Path(
        "services/api/migrations/versions/0030_volunteer_entry_reference_expiration.py"
    ).read_text(encoding="utf-8")
    assert "entry.expires_at > now()" in migration
    assert "nullable=False" in migration
    assert "organization_code varchar" in migration
    assert "organization_name varchar" in migration
    assert "VOLATILE" in migration
    assert "FOR UPDATE OF entry, organization" in migration
    assert "app.auth_exact_org_id" in migration
    assert 'for table in ("volunteer_applications", "volunteer_access_grants")' in migration
    assert "CREATE POLICY {table}_tenant_scope" in migration
