"""Offline report template/verification. Never contacts LINE or records a PASS."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from services.api.app.config.line_menu_smoke import (
    Report,
    config_digest,
    digest,
    evidence_requirements,
    expected_report_environment,
    protected_bytes,
    protected_json,
    release_identity,
    required_resources,
    scope_digest,
    utc,
    validate_report,
)
from services.api.app.config.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("template", "validate"))
    parser.add_argument("--config-env", type=Path, required=True)
    parser.add_argument("--release-manifest", required=True)
    parser.add_argument("--resources", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument(
        "--kind", choices=("real-line", "automated-fixture"), default="automated-fixture"
    )
    args = parser.parse_args()
    try:
        # Only menu/public identity settings. Do not source shell or load .env/secrets.
        allowed = {key for key in Settings.model_fields if key.startswith("line_rich_menu_")}
        allowed |= {
            "app_env",
            "line_channel_id",
            "line_role_menu_bot_sha256",
            "web_public_base_url",
            "liff_id",
            "line_staff_liff_id",
            "line_staff_menu_enabled",
            "line_role_menu_report_sha256",
            "line_role_menu_test_channel_id",
            "line_role_menu_test_user_sha256",
            "line_role_menu_test_expires_at",
        }
        values = {}
        for line in protected_bytes(str(args.config_env)).decode().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.lower() in allowed:
                if key.lower() in values:
                    raise ValueError("duplicate configuration")
                values[key.lower()] = value
        # Explicit empty defaults defeat ambient environment values.
        configured = {key: values.get(key, "") for key in allowed}
        configured["line_staff_menu_enabled"] = values.get("line_staff_menu_enabled", "false")
        settings = Settings(_env_file=None, **configured)
        settings.line_role_menu_release_file = args.release_manifest
        settings.line_role_menu_resources_file = args.resources
        settings.line_role_menu_report_file = args.report
        if args.operation == "validate":
            validate_report(settings)
            print("Report contract PASS (operator attestation; not proof of human truth)")
            return
        manifest, _ = protected_json(args.release_manifest)
        resources, _ = protected_json(args.resources)
        requirements = evidence_requirements(settings)
        selected_resources = required_resources(settings, resources)
        report = {
            "schema_version": 1,
            "kind": args.kind,
            "environment": (
                "isolated-test"
                if args.kind == "automated-fixture"
                else expected_report_environment(settings)
            ),
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "candidate": release_identity(manifest).model_dump(),
            "channel_id": settings.line_channel_id,
            "bot_sha256": settings.line_role_menu_bot_sha256,
            "scope_sha256": scope_digest(settings),
            "scope_expires_at": utc(settings.line_role_menu_test_expires_at).isoformat(),
            "config_sha256": config_digest(settings),
            "resources": {role: menu.model_dump() for role, menu in selected_resources.items()},
            "roles": list(requirements.roles),
            "identity_protection": "protected-config-hashes-no-uid",
            "cases": {
                name: {"result": "NOT RUN", "source": "human", "reference": "pending"}
                for name in sorted(requirements.human_cases)
            },
        }
        report["cases"]["resources.readback"] = {
            "result": "NOT RUN",
            "source": "automated",
            "reference": "pending",
        }
        Report.model_validate(report)
        raw = (json.dumps(report, indent=2) + "\n").encode()
        fd = os.open(args.report, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        print("Template only: all cases NOT RUN; sha256=" + digest(raw))
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, "Evidence operation rejected; check protected inputs (values suppressed)\n")


if __name__ == "__main__":
    main()
