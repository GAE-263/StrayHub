"""Simulated attestation contract fixtures; never evidence of real LINE operations."""

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from pydantic import SecretStr
from services.api.app.config.line_menu_smoke import (
    config_digest,
    evidence_requirements,
    scope_digest,
)


def _report_fixture(settings, tmp_path, *, kind: str):
    settings.line_role_menu_bot_sha256 = "b" * 64
    settings.line_channel_id = "1234567890"
    settings.line_role_menu_test_channel_id = settings.line_channel_id
    settings.line_role_menu_test_user_sha256 = SecretStr("2" * 64)
    # Keep the synthetic scope valid long enough for validation without recording a UID.
    settings.line_role_menu_test_expires_at = (
        (datetime.now(timezone.utc) + timedelta(hours=1)).replace(microsecond=0).isoformat()
    )
    if settings.line_staff_menu_enabled and not settings.line_rich_menu_staff_id:
        settings.line_rich_menu_staff_id = "richmenu-synthetic-staff"
    manifest = {
        "git_sha": "a" * 40,
        "compose_sha256": "c" * 64,
        "release_bundle_sha256": "d" * 64,
        "images": {
            role: {"repository": f"synthetic/{role}", "digest": "sha256:" + "e" * 64}
            for role in ("api", "worker", "web")
        },
    }
    requirements = evidence_requirements(settings)
    resources = {
        role: {
            "id": getattr(settings, f"line_rich_menu_{role}_id"),
            "definition_sha256": "f" * 64,
            "image_sha256": "1" * 64,
        }
        for role in requirements.resource_roles
    }
    report = {
        "schema_version": 1,
        "kind": kind,
        "environment": "production" if kind == "real-line" else "isolated-test",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "candidate": manifest,
        "channel_id": settings.line_channel_id,
        "bot_sha256": settings.line_role_menu_bot_sha256,
        "scope_sha256": scope_digest(settings),
        "scope_expires_at": settings.line_role_menu_test_expires_at,
        "config_sha256": config_digest(settings),
        "resources": resources,
        "roles": list(requirements.roles),
        "identity_protection": "protected-config-hashes-no-uid",
        "cases": {
            case: {
                "result": "PASS",
                "source": "human" if kind == "real-line" else "automated",
                "reference": "schema-fixture-only",
            }
            for case in requirements.human_cases
        },
    }
    report["cases"]["resources.readback"] = {
        "result": "PASS",
        "source": "automated",
        "reference": "synthetic-only",
    }
    for field, document in (("release", manifest), ("resources", resources), ("report", report)):
        path = tmp_path / f"{field}.json"
        path.write_text(json.dumps(document))
        path.chmod(0o600)
        setattr(settings, f"line_role_menu_{field}_file", str(path))
    settings.line_role_menu_report_sha256 = sha256(
        (tmp_path / "report.json").read_bytes()
    ).hexdigest()
    return report


def real_report_fixture(settings, tmp_path):
    """Build a structurally real operator-report fixture for validator unit tests only."""
    return _report_fixture(settings, tmp_path, kind="real-line")


def simulated_report(settings, tmp_path):
    """Build isolated automated evidence that production validation must reject."""
    return _report_fixture(settings, tmp_path, kind="automated-fixture")
