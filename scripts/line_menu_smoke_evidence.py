"""Offline report template/verification. Never contacts LINE or records a PASS."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
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
    parser.add_argument(
        "operation",
        choices=("template", "validate", "approve", "direct-template", "authorize-direct"),
    )
    parser.add_argument("--config-env", type=Path, required=True)
    parser.add_argument("--release-manifest", required=True)
    parser.add_argument("--resources", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--output", type=Path, help="New immutable approved report")
    parser.add_argument("--confirmation", default="")
    parser.add_argument("--reference", default="")
    parser.add_argument(
        "--kind", choices=("real-line", "automated-fixture"), default="automated-fixture"
    )
    parser.add_argument("--schema-version", type=int, choices=(1, 2), default=1)
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
            "celery_ai_enabled",
            "gemini_model_name",
            "gemini_vertex_location",
            "ai_provider",
            "ai_model_name",
            "ai_endpoint",
        }
        values = {}
        for line in protected_bytes(str(args.config_env)).decode().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.lower() in allowed:
                if key.lower() in values:
                    raise ValueError("duplicate configuration")
                values[key.lower()] = value
        # Explicit empty defaults defeat ambient environment values.
        configured = {key: values.get(key, Settings.model_fields[key].default) for key in allowed}
        configured["line_staff_menu_enabled"] = values.get("line_staff_menu_enabled", "false")
        settings = Settings(_env_file=None, **configured)
        settings.line_role_menu_release_file = args.release_manifest
        settings.line_role_menu_resources_file = args.resources
        settings.line_role_menu_report_file = args.report
        if args.operation in {"direct-template", "authorize-direct"}:
            from services.api.app.config.line_menu_approval import DirectOpening, evidence_digest

            manifest, _ = protected_json(args.release_manifest)
            resources, _ = protected_json(args.resources)
            if settings.line_staff_menu_enabled or settings.app_env != "production":
                raise ValueError("direct opening scope")
            if args.operation == "direct-template":
                data = {
                    "schema_version": 3,
                    "kind": "operator-authorized-direct-opening",
                    "environment": "production",
                    "candidate": release_identity(manifest).model_dump(),
                    "channel_id": settings.line_channel_id,
                    "bot_sha256": settings.line_role_menu_bot_sha256,
                    "config_sha256": config_digest(settings, include_ai=True),
                    "resources": {
                        role: menu.model_dump()
                        for role, menu in required_resources(settings, resources).items()
                    },
                    "human_validation": "NOT RUN",
                    "accept_unverified_user_flows": True,
                    "staff_enabled": False,
                    "approval": {
                        "status": "pending",
                        "operator": "yawan0203",
                        "approved_at": "",
                        "evidence_sha256": "0" * 64,
                        "reference": "pending",
                    },
                }
                DirectOpening.model_validate(data)
                output_path = Path(args.report)
            else:
                data, checksum = protected_json(args.report)
                direct = DirectOpening.model_validate(data)
                if (
                    direct.approval.status != "pending"
                    or args.output is None
                    or args.confirmation
                    != f"AUTHORIZE DIRECT LINE OPEN {direct.candidate.git_sha} {checksum}"
                ):
                    raise ValueError("explicit direct opening confirmation required")
                data["approval"] = {
                    "status": "approved",
                    "operator": "yawan0203",
                    "approved_at": datetime.now(timezone.utc).isoformat(),
                    "evidence_sha256": evidence_digest(data),
                    "reference": args.reference,
                }
                from services.api.app.config.line_menu_approval import validate_direct_opening

                validate_direct_opening(data, settings, manifest, resources)
                output_path = args.output
            raw = (json.dumps(data, indent=2) + "\n").encode()
            fd = os.open(output_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            print("Direct opening attestation; human_validation=NOT RUN; sha256=" + digest(raw))
            return
        if args.operation == "approve":
            from services.api.app.config.line_menu_approval import evidence_digest
            from services.api.app.config.line_menu_smoke import _scope_contract_valid

            data, checksum = protected_json(args.report)
            if (
                args.output is None
                or args.confirmation != f"APPROVE LINE EVIDENCE {checksum}"
                or data.get("schema_version") != 2
                or data.get("approval", {}).get("status") != "pending"
                or not _scope_contract_valid(settings)
                or data["evidence"]["scope_sha256"] != scope_digest(settings)
            ):
                raise ValueError("approval requires reviewed pending evidence and active scope")
            data["approval"] = {
                "status": "approved",
                "operator": "yawan0203",
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "evidence_sha256": evidence_digest(data),
                "reference": args.reference,
            }
            raw = (json.dumps(data, indent=2) + "\n").encode()
            with tempfile.NamedTemporaryFile(prefix="line-evidence-validation-") as pending:
                pending.write(raw)
                pending.flush()
                settings.line_role_menu_report_file = pending.name
                settings.line_role_menu_report_sha256 = digest(raw)
                validate_report(settings)
            fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            print("Approved protected operator attestation; sha256=" + digest(raw))
            return
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
            "config_sha256": config_digest(settings, include_ai=args.schema_version == 2),
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
        if args.schema_version == 2:
            from services.api.app.config.line_menu_approval import ApprovedReport, snapshot

            evidence = report
            report = {
                "schema_version": 2,
                "account_mode": "single-account-staged",
                "evidence": evidence,
                "scope": snapshot(settings),
                "stages": {
                    name: {
                        "observed_at": evidence["observed_at"],
                        "principal_reference": "account-1",
                        "membership": "VOLUNTEER"
                        if name.startswith("volunteer.")
                        else ("STAFF" if name.startswith("staff.") else "public"),
                        "scope_sha256": evidence["scope_sha256"],
                        "scope_state": {
                            "boundary.non_test_unchanged": "outside",
                            "boundary.expired_denied": "expired",
                            "boundary.cross_tenant_denied": "cross-tenant",
                        }.get(name, "allowed"),
                    }
                    for name in requirements.human_cases
                },
                "approval": {
                    "status": "pending",
                    "operator": "yawan0203",
                    "approved_at": "",
                    "evidence_sha256": "0" * 64,
                    "reference": "pending",
                },
            }
            ApprovedReport.model_validate(report)
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
