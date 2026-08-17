from pathlib import Path


def test_all_volunteer_resources_are_tenant_scoped_and_force_rls_protected() -> None:
    migration = Path("services/api/migrations/versions/0024_volunteer_access_expand.py").read_text()
    repository = Path(
        "services/api/app/persistence/repositories/volunteer_access_repository.py"
    ).read_text()
    tables = [
        "volunteer_applications",
        "volunteer_access_grants",
        "volunteer_decision_batches",
        "volunteer_decision_batch_items",
        "volunteer_notification_deliveries",
        "volunteer_notification_retry_batches",
        "volunteer_notification_retry_batch_items",
    ]
    for table in tables:
        assert table in migration
    assert 'op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")' in migration
    assert "self.organization_id" in repository
    assert "organization_scope_mismatch" in repository
