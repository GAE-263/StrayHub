from pathlib import Path

EXPAND = Path("services/api/migrations/versions/0024_volunteer_access_expand.py")
ENFORCE = Path("services/api/migrations/versions/0025_volunteer_access_enforce.py")
SYSTEM_ACTOR = Path("services/api/migrations/versions/0026_audit_system_actor.py")
INSURANCE_POLICY = Path("services/api/migrations/versions/0031_volunteer_insurance_policy.py")


def test_two_phase_migration_declares_policy_staging_and_single_head_chain() -> None:
    assert EXPAND.exists()
    assert ENFORCE.exists()
    expand = EXPAND.read_text()
    enforce = ENFORCE.read_text()
    assert 'revision = "0024_volunteer_access_expand"' in expand
    assert 'down_revision = "0023_obs_vocab_management"' in expand
    assert 'revision = "0025_volunteer_access_enforce"' in enforce
    assert 'down_revision = "0024_volunteer_access_expand"' in enforce
    assert "default_grant_duration_hours" in expand
    assert "SYSTEM_MIGRATION" in enforce
    assert SYSTEM_ACTOR.exists()
    assert 'down_revision = "0025_volunteer_access_enforce"' in SYSTEM_ACTOR.read_text()


def test_enforce_backfill_only_targets_active_unbounded_volunteers() -> None:
    enforce = ENFORCE.read_text()
    assert "role = 'VOLUNTEER'" in enforce
    assert "status = 'active'" in enforce
    assert "expires_at IS NULL" in enforce
    assert "disabled" not in enforce.lower() or "status = 'active'" in enforce
    assert "legacy_migration" in enforce


def test_expand_enables_force_rls_and_fixed_entry_resolver() -> None:
    expand = EXPAND.read_text()
    assert "FORCE ROW LEVEL SECURITY" in expand
    assert "resolve_volunteer_entry_reference" in expand
    assert "SECURITY DEFINER" in expand
    assert "SET search_path" in expand
    assert "strayhub_runtime" in expand


def test_insurance_policy_migration_declares_exact_chain_and_safe_column() -> None:
    assert INSURANCE_POLICY.exists()
    migration = INSURANCE_POLICY.read_text()

    assert 'revision = "0031_volunteer_insurance_policy"' in migration
    assert 'down_revision = "0030_volunteer_entry_expiry"' in migration
    assert "op.add_column(" in migration
    assert '"organization_volunteer_access_policies"' in migration
    assert '"insurance_required"' in migration
    assert "sa.Boolean()" in migration
    assert 'server_default=sa.text("false")' in migration
    assert "nullable=False" in migration
    assert (
        'op.drop_column("organization_volunteer_access_policies", "insurance_required")'
        in migration
    )
