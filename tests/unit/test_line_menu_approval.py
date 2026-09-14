"""Synthetic schema fixtures only; never real LINE/human evidence."""

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import SecretStr
from services.api.app.config.line_menu_approval import evidence_digest, snapshot
from services.api.app.config.line_menu_smoke import (
    config_digest,
    digest,
    scope_digest,
    validate_report,
)
from tests.unit.test_line_menu_smoke_scope import report_settings, scoped_settings


def save(settings, document):
    path = Path(settings.line_role_menu_report_file)
    path.write_text(json.dumps(document))
    settings.line_role_menu_report_sha256 = digest(path.read_bytes())


def approved_fixture(tmp_path, *, days_ago=30):
    settings, report = report_settings(tmp_path)
    observed = datetime.now(timezone.utc) - timedelta(days=days_ago, minutes=5)
    settings.line_role_menu_test_expires_at = (observed + timedelta(hours=1)).isoformat()
    report.update(
        observed_at=observed.isoformat(),
        scope_sha256=scope_digest(settings),
        scope_expires_at=settings.line_role_menu_test_expires_at,
        config_sha256=config_digest(settings, include_ai=True),
    )
    boundary = {
        "non_test_unchanged": "outside",
        "expired_denied": "expired",
        "cross_tenant_denied": "cross-tenant",
    }
    document = {
        "schema_version": 2,
        "account_mode": "single-account-staged",
        "evidence": report,
        "scope": snapshot(settings),
        "stages": {
            name: {
                "observed_at": (
                    observed - timedelta(minutes=2 if name.startswith("adopter.") else 1)
                ).isoformat(),
                "principal_reference": "account-1",
                "membership": "VOLUNTEER" if name.startswith("volunteer.") else "public",
                "scope_sha256": report["scope_sha256"],
                "scope_state": boundary.get(name.split(".")[-1], "allowed"),
            }
            for name, case in report["cases"].items()
            if case["source"] == "human"
        },
        "approval": {
            "status": "approved",
            "operator": "yawan0203",
            "approved_at": (observed + timedelta(minutes=1)).isoformat(),
            "evidence_sha256": "0" * 64,
            "reference": "synthetic-fixture-only",
        },
    }
    document["approval"]["evidence_sha256"] = evidence_digest(document)
    save(settings, document)
    return settings, document


def test_approved_exact_version_restarts_without_expired_test_scope(tmp_path):
    settings, _ = approved_fixture(tmp_path)
    settings.line_role_menu_test_user_sha256 = SecretStr("")
    settings.line_role_menu_test_expires_at = ""
    settings.line_role_menu_test_channel_id = ""
    validate_report(settings)
    settings.validate_runtime_safety()


def test_expired_bounded_scope_still_denies_access():
    settings = scoped_settings(line_role_menu_test_expires_at="2020-01-01T00:00:00+00:00")
    assert not settings.line_role_menu_allowed("U" + "1" * 32)


@pytest.mark.parametrize(
    "fault",
    [
        "pending",
        "revoked",
        "operator",
        "hash",
        "future",
        "late",
        "scope",
        "scope_expiry",
        "stage_missing",
        "stage_role",
        "stage_time",
        "stage_account",
        "stage_order",
        "stage_scope",
        "boundary",
        "fixture",
        "source",
        "fail",
        "candidate",
        "images",
        "resources",
        "environment",
    ],
)
def test_invalid_approval_or_evidence_denied(tmp_path, fault):
    settings, doc = approved_fixture(tmp_path)
    report = doc["evidence"]
    if fault in {"pending", "revoked"}:
        doc["approval"]["status"] = fault
    elif fault == "operator":
        doc["approval"]["operator"] = "not-operator"
    elif fault == "hash":
        doc["approval"]["evidence_sha256"] = "0" * 64
    elif fault == "future":
        doc["approval"]["approved_at"] = "2099-01-01T00:00:00+00:00"
    elif fault == "late":
        doc["approval"]["approved_at"] = datetime.now(timezone.utc).isoformat()
    elif fault == "scope":
        doc["scope"]["channel_id"] = "999"
    elif fault == "scope_expiry":
        doc["scope"]["expires_at"] = "2020-01-01T00:00:00+00:00"
    elif fault == "stage_missing":
        del doc["stages"]["adopter.default_hub"]
    elif fault == "stage_role":
        doc["stages"]["volunteer.walk_authorized"]["membership"] = "public"
    elif fault == "stage_time":
        doc["stages"]["adopter.default_hub"]["observed_at"] = "2099-01-01T00:00:00+00:00"
    elif fault == "stage_account":
        doc["stages"]["volunteer.walk_authorized"]["principal_reference"] = "account-2"
    elif fault == "stage_order":
        doc["stages"]["adopter.default_hub"]["observed_at"] = report["observed_at"]
    elif fault == "stage_scope":
        doc["stages"]["adopter.default_hub"]["scope_sha256"] = "0" * 64
    elif fault == "boundary":
        doc["stages"]["boundary.expired_denied"]["scope_state"] = "allowed"
    elif fault == "fixture":
        report["kind"] = "automated-fixture"
    elif fault == "source":
        report["cases"]["adopter.default_hub"]["source"] = "automated"
    elif fault == "fail":
        report["cases"]["adopter.default_hub"]["result"] = "FAIL"
    elif fault == "candidate":
        report["candidate"]["git_sha"] = "f" * 40
    elif fault == "images":
        report["candidate"]["images"]["api"]["digest"] = "sha256:" + "f" * 64
    elif fault == "resources":
        report["resources"]["default"]["image_sha256"] = "0" * 64
    elif fault == "environment":
        report["environment"] = "production-like"
    if fault != "hash":
        doc["approval"]["evidence_sha256"] = evidence_digest(doc)
    save(settings, doc)
    with pytest.raises(ValueError, match="report invalid"):
        validate_report(settings)


@pytest.mark.parametrize(
    "field,value",
    [
        ("celery_ai_enabled", True),
        ("gemini_model_name", "different-model"),
        ("line_channel_id", "999"),
        ("line_staff_menu_enabled", True),
    ],
)
def test_runtime_configuration_change_requires_reapproval(tmp_path, field, value):
    settings, _ = approved_fixture(tmp_path)
    setattr(settings, field, value)
    with pytest.raises(ValueError, match="report invalid"):
        validate_report(settings)


def test_legacy_schema_does_not_gain_durable_approval(tmp_path):
    settings, doc = approved_fixture(tmp_path)
    legacy = copy.deepcopy(doc["evidence"])
    legacy["config_sha256"] = config_digest(settings)
    save(settings, legacy)
    with pytest.raises(ValueError, match="report invalid"):
        validate_report(settings)


def test_modified_case_cannot_reuse_approval_even_with_new_file_checksum(tmp_path):
    settings, document = approved_fixture(tmp_path)
    document["evidence"]["cases"]["adopter.default_hub"]["reference"] = "different"
    save(settings, document)
    with pytest.raises(ValueError, match="report invalid"):
        validate_report(settings)


@pytest.mark.parametrize("key", ["schema_version", "kind", "membership"])
def test_duplicate_keys_at_any_evidence_level_denied(tmp_path, key):
    settings, document = approved_fixture(tmp_path)
    raw = json.dumps(document)
    marker = f'"{key}":'
    # Duplicate with the same value still must be rejected recursively.
    start = raw.index(marker)
    end = raw.index(",", start)
    raw = raw[:start] + raw[start : end + 1] + raw[start:]
    path = Path(settings.line_role_menu_report_file)
    path.write_text(raw)
    settings.line_role_menu_report_sha256 = digest(path.read_bytes())
    with pytest.raises(ValueError, match="report invalid"):
        validate_report(settings)


def test_revocation_and_permissions_are_checked_at_each_validation(tmp_path):
    settings, document = approved_fixture(tmp_path)
    validate_report(settings)
    document["approval"]["status"] = "revoked"
    save(settings, document)
    with pytest.raises(ValueError, match="report invalid"):
        validate_report(settings)
    document["approval"]["status"] = "approved"
    save(settings, document)
    Path(settings.line_role_menu_report_file).chmod(0o666)
    with pytest.raises(ValueError, match="report invalid"):
        validate_report(settings)


def test_schema_two_template_is_pending_and_cannot_authorize(tmp_path):
    import os
    import subprocess
    import sys

    settings, _ = report_settings(tmp_path)
    keys = [
        "app_env",
        "line_channel_id",
        "line_role_menu_bot_sha256",
        "line_role_menu_test_channel_id",
        "line_role_menu_test_expires_at",
    ]
    config = tmp_path / "config.env"
    config.write_text(
        "\n".join(f"{key.upper()}={getattr(settings, key)}" for key in keys)
        + "\nLINE_ROLE_MENU_TEST_USER_SHA256="
        + settings.line_role_menu_test_user_sha256.get_secret_value()
        + "\nLINE_RICH_MENU_DEFAULT_ID=richmenu-default"
        "\nLINE_RICH_MENU_VOLUNTEER_ID=richmenu-volunteer"
        "\nLINE_RICH_MENU_ADOPTION_HUB_ID=richmenu-hub\n"
    )
    config.chmod(0o600)
    output = tmp_path / "pending.json"
    command = [
        sys.executable,
        "-m",
        "scripts.line_menu_smoke_evidence",
        "template",
        "--schema-version",
        "2",
        "--kind",
        "real-line",
        "--config-env",
        str(config),
        "--release-manifest",
        settings.line_role_menu_release_file,
        "--resources",
        settings.line_role_menu_resources_file,
        "--report",
        str(output),
    ]
    result = subprocess.run(
        command, env={"PATH": os.environ["PATH"]}, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    document = json.loads(output.read_text())
    assert document["approval"]["status"] == "pending"
    assert all(c["result"] == "NOT RUN" for c in document["evidence"]["cases"].values())
    save(settings, document)
    with pytest.raises(ValueError, match="report invalid"):
        validate_report(settings)
