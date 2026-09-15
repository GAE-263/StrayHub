"""Synthetic direct-opening authorization, never human PASS evidence."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from services.api.app.config.line_menu_approval import evidence_digest
from services.api.app.config.line_menu_smoke import config_digest, digest, validate_report
from tests.unit.test_line_menu_smoke_scope import report_settings


def direct_fixture(tmp_path):
    settings, evidence = report_settings(tmp_path)
    settings.line_staff_menu_enabled = False
    settings.line_role_menu_test_enabled = False
    doc = {
        "schema_version": 3,
        "kind": "operator-authorized-direct-opening",
        "environment": "production",
        "candidate": evidence["candidate"],
        "channel_id": settings.line_channel_id,
        "bot_sha256": settings.line_role_menu_bot_sha256,
        "config_sha256": config_digest(settings, include_ai=True),
        "resources": {k: v for k, v in evidence["resources"].items() if k != "staff"},
        "human_validation": "NOT RUN",
        "accept_unverified_user_flows": True,
        "staff_enabled": False,
        "approval": {
            "status": "approved",
            "operator": "yawan0203",
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "reference": "synthetic-direct-authorization",
            "evidence_sha256": "0" * 64,
        },
    }
    doc["approval"]["evidence_sha256"] = evidence_digest(doc)
    save(settings, doc)
    return settings, doc


def save(settings, doc):
    raw = json.dumps(doc).encode()
    Path(settings.line_role_menu_report_file).write_bytes(raw)
    settings.line_role_menu_report_sha256 = digest(raw)


def test_explicit_direct_opening_preserves_not_run(tmp_path):
    settings, doc = direct_fixture(tmp_path)
    validate_report(settings)
    assert doc["human_validation"] == "NOT RUN"
    assert "cases" not in doc


@pytest.mark.parametrize(
    "fault",
    [
        "pending",
        "revoked",
        "operator",
        "checksum",
        "future",
        "sha",
        "images",
        "channel",
        "bot",
        "config",
        "resources",
        "human_pass",
        "risk",
        "staff",
        "test",
        "extra",
    ],
)
def test_direct_opening_fail_closed(tmp_path, fault):
    settings, doc = direct_fixture(tmp_path)
    if fault in ["pending", "revoked"]:
        doc["approval"]["status"] = fault
    elif fault == "operator":
        doc["approval"]["operator"] = "other"
    elif fault == "checksum":
        doc["approval"]["evidence_sha256"] = "0" * 64
    elif fault == "future":
        doc["approval"]["approved_at"] = "2099-01-01T00:00:00+00:00"
    elif fault == "sha":
        doc["candidate"]["git_sha"] = "b" * 40
    elif fault == "images":
        doc["candidate"]["images"]["api"]["digest"] = "sha256:" + "b" * 64
    elif fault == "channel":
        doc["channel_id"] = "999"
    elif fault == "bot":
        doc["bot_sha256"] = "f" * 64
    elif fault == "config":
        doc["config_sha256"] = "b" * 64
    elif fault == "resources":
        doc["resources"]["default"]["id"] = "richmenu-wrong"
    elif fault == "human_pass":
        doc["human_validation"] = "PASS"
    elif fault == "risk":
        doc["accept_unverified_user_flows"] = False
    elif fault == "staff":
        settings.line_staff_menu_enabled = True
    elif fault == "test":
        settings.line_role_menu_test_enabled = True
    elif fault == "extra":
        doc["skip_auth"] = True
    if fault != "checksum":
        doc["approval"]["evidence_sha256"] = evidence_digest(doc)
    save(settings, doc)
    with pytest.raises(ValueError):
        validate_report(settings)


@pytest.mark.parametrize("wrong_confirmation", [False, True])
def test_direct_cli_requires_exact_confirmation_and_preserves_not_run(tmp_path, wrong_confirmation):
    import subprocess
    import sys

    settings, _ = direct_fixture(tmp_path)
    config = tmp_path / "public-config.env"
    allowed = [key for key in type(settings).model_fields if key.startswith("line_rich_menu_")]
    allowed += [
        "app_env",
        "line_channel_id",
        "line_role_menu_bot_sha256",
        "web_public_base_url",
        "liff_id",
        "line_staff_menu_enabled",
        "celery_ai_enabled",
        "gemini_model_name",
        "gemini_vertex_location",
        "ai_provider",
        "ai_model_name",
        "ai_endpoint",
    ]
    lines = []
    for key in allowed:
        value = getattr(settings, key)
        if value is not None:
            rendered = str(value).lower() if isinstance(value, bool) else str(value)
            lines.append(f"{key.upper()}={rendered}")
    config.write_text("\n".join(lines))
    pending = tmp_path / "pending.json"
    approved = tmp_path / "approved.json"
    common = [
        "--config-env",
        str(config),
        "--release-manifest",
        settings.line_role_menu_release_file,
        "--resources",
        settings.line_role_menu_resources_file,
        "--report",
        str(pending),
    ]
    first = subprocess.run(
        [sys.executable, "-m", "scripts.line_menu_smoke_evidence", "direct-template", *common],
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    document = json.loads(pending.read_bytes())
    assert document["approval"]["status"] == "pending"
    pending_hash = digest(pending.read_bytes())
    confirmation = f"AUTHORIZE DIRECT LINE OPEN {document['candidate']['git_sha']} {pending_hash}"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.line_menu_smoke_evidence",
            "authorize-direct",
            *common,
            "--output",
            str(approved),
            "--reference",
            "synthetic-user-risk-acceptance",
            "--confirmation",
            "wrong" if wrong_confirmation else confirmation,
        ],
        capture_output=True,
        text=True,
    )
    if wrong_confirmation:
        assert result.returncode != 0 and not approved.exists()
    else:
        assert result.returncode == 0, result.stderr
        assert json.loads(approved.read_bytes())["human_validation"] == "NOT RUN"
        assert json.loads(pending.read_bytes())["approval"]["status"] == "pending"
        settings.line_role_menu_report_file = str(approved)
        settings.line_role_menu_report_sha256 = digest(approved.read_bytes())
        validate_report(settings)
