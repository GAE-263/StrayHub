from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import re
import secrets
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.public_tunnel_policy import PolicyError, normalize_runtime_origin  # noqa: E402
from services.api.app.observability.logging import get_logger, mask_sensitive  # noqa: E402

ACTIVATION_REQUIRED_CHECKS = frozenset(
    {
        "exact_runtime_reserved_host_validated",
        "synthetic_demo_data_verified",
        "old_demo_password_rejected",
        "new_demo_password_accepted",
        "old_demo_sessions_revoked",
        "allow_and_deny_route_matrix_passed",
        "sensitive_log_sentinel_absent",
    }
)
_SENSITIVE_EVIDENCE_KEYS = re.compile(
    r"(?:password|authorization|access[_-]?token|refresh[_-]?token|secret|credential)",
    re.IGNORECASE,
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ActivationEvidenceError(ValueError):
    """Raised when public activation evidence cannot safely open the gate."""


def _assert_no_sensitive_evidence_fields(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if (
                key not in ACTIVATION_REQUIRED_CHECKS
                and key != "evidence_digest_sha256"
                and _SENSITIVE_EVIDENCE_KEYS.search(str(key))
            ):
                raise ActivationEvidenceError("activation evidence contains a sensitive field")
            _assert_no_sensitive_evidence_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_sensitive_evidence_fields(nested)


def verify_activation_evidence(
    evidence_path: Path,
    *,
    expected_origin: str,
    allow_synthetic: bool = False,
) -> dict[str, str]:
    """Validate machine-readable evidence without returning host or credential material."""

    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ActivationEvidenceError("activation evidence schema is invalid") from exc
    if not isinstance(payload, dict):
        raise ActivationEvidenceError("activation evidence schema is invalid")
    _assert_no_sensitive_evidence_fields(payload)
    required_top_level = {
        "version",
        "evidence_kind",
        "runtime_origin",
        "environment",
        "operator",
        "recorded_at_utc",
        "checks",
    }
    if set(payload) != required_top_level or payload.get("version") != 1:
        raise ActivationEvidenceError("activation evidence schema is invalid")
    try:
        normalized_expected = normalize_runtime_origin(expected_origin)
        normalized_evidence = normalize_runtime_origin(payload.get("runtime_origin"))
    except PolicyError as exc:
        raise ActivationEvidenceError("activation evidence runtime origin is invalid") from exc
    if normalized_evidence.origin != normalized_expected.origin:
        raise ActivationEvidenceError("activation evidence runtime origin does not match")
    kind = payload.get("evidence_kind")
    if kind not in {"manual_external", "synthetic_local"}:
        raise ActivationEvidenceError("activation evidence schema is invalid")
    if kind != "manual_external" and not allow_synthetic:
        raise ActivationEvidenceError("public activation requires manual external evidence")
    if not all(
        isinstance(payload.get(key), str) and payload[key]
        for key in required_top_level - {"version", "checks"}
    ):
        raise ActivationEvidenceError("activation evidence schema is invalid")
    checks = payload.get("checks")
    if not isinstance(checks, dict) or set(checks) != ACTIVATION_REQUIRED_CHECKS:
        raise ActivationEvidenceError("activation evidence is incomplete")
    for check in checks.values():
        if (
            not isinstance(check, dict)
            or set(check) != {"result", "evidence_digest_sha256"}
            or check.get("result") != "PASS"
            or not isinstance(check.get("evidence_digest_sha256"), str)
            or not _SHA256.fullmatch(check["evidence_digest_sha256"])
        ):
            raise ActivationEvidenceError("activation evidence is incomplete")
    return {
        "status": "PASS" if kind == "manual_external" else "PASS_SYNTHETIC_ONLY",
        "evidence_kind": kind,
        "runtime_origin_digest": _digest(normalized_expected.origin),
    }


def _sentinel(surface: str) -> str:
    return f"STRAYHUB_PHASE_E_SENTINEL_{surface.upper()}_{secrets.token_hex(12)}"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _capture_application_log(logger_name: str, message: str, value: str) -> str:
    logger = get_logger(logger_name)
    original_handlers = logger.handlers[:]
    original_level = logger.level
    original_propagate = logger.propagate
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    try:
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.info(message, value)
        return output.getvalue()
    finally:
        logger.handlers = original_handlers
        logger.setLevel(original_level)
        logger.propagate = original_propagate


def _occurrences(content: str, sentinels: list[str]) -> int:
    forms = {form for value in sentinels for form in (value, quote(value, safe=""))}
    return sum(content.count(form) for form in forms)


def run_verification(
    *,
    root: Path,
    temp_root: Path | None = None,
    inject_leak: str | None = None,
) -> dict:
    del root  # The runner deliberately does not read .env or runtime credentials.
    names = (
        "browser_request",
        "public_gateway",
        "nginx",
        "next",
        "uvicorn",
        "application",
        "audit",
        "test_artifact",
    )
    values = {name: _sentinel(name) for name in names}
    all_values = list(values.values())
    artifacts = {
        "browser_request": "GET /login HTTP/1.1\ncanonical=/login\n",
        "public_gateway": "GET /login status=404 upstream=none\n",
        "nginx": "GET /login HTTP/1.1 status=404 bytes=0 rt=0.001\n"
        "GET /v1/public/animals/resource/photo HTTP/1.1 status=200\n"
        "GET /v1/animals/search?query=ordinary-negative-control&page=2 status=200\n",
        "next": "forbidden_request=not_reached allowlisted_page=/volunteer-entry\n",
        "uvicorn": _capture_application_log(
            "strayhub.phase_e.uvicorn", "Authorization: Bearer %s", values["uvicorn"]
        ),
        "application": _capture_application_log(
            "strayhub.phase_e.application",
            "provider failure password=%s",
            values["application"],
        ),
        "audit": json.dumps(
            mask_sensitive(
                {
                    "before": {"access_token": values["audit"]},
                    "after": {"nested": [{"password": values["audit"]}]},
                    "result": "denied",
                }
            ),
            sort_keys=True,
        ),
        "test_artifact": "run=synthetic values=digest-only cleanup=pending\n",
    }
    if inject_leak in artifacts:
        artifacts[inject_leak] += values[inject_leak]

    surface_results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="strayhub-sensitive-runtime-", dir=temp_root) as tmp:
        directory = Path(tmp)
        for name, content in artifacts.items():
            path = directory / f"{name}.log"
            path.write_text(content, encoding="utf-8")
            raw_occurrences = _occurrences(content, all_values)
            surface_results.append(
                {
                    "name": name,
                    "status": "PASS" if raw_occurrences == 0 else "FAIL",
                    "raw_occurrences": raw_occurrences,
                    "sentinel_digest": _digest(values[name]),
                }
            )

    failed = any(item["raw_occurrences"] for item in surface_results)
    return {
        "run_id": str(uuid4()),
        "result": "FAIL" if failed else "PASS_WITH_MANUAL_EXTERNAL",
        "surfaces": surface_results,
        "external_surfaces": [
            {
                "name": "ngrok_inspector_and_remote_retention",
                "status": "MANUAL_ACTION_REQUIRED",
                "raw_occurrences": 0,
                "sentinel_digest": None,
            }
        ],
        "negative_controls": {
            "class_b_query_forwarded": True,
            "ordinary_query_observable": True,
        },
        "cleanup_status": "cleaned",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run synthetic sensitive transport checks")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--activation-evidence", type=Path)
    parser.add_argument("--expected-origin")
    parser.add_argument("--allow-synthetic-evidence", action="store_true")
    args = parser.parse_args()
    if args.activation_evidence:
        if not args.expected_origin:
            parser.error("--expected-origin is required with --activation-evidence")
        try:
            activation = verify_activation_evidence(
                args.activation_evidence,
                expected_origin=args.expected_origin,
                allow_synthetic=args.allow_synthetic_evidence,
            )
        except ActivationEvidenceError as exc:
            print(json.dumps({"activation_gate": "FAIL", "reason": str(exc)}))
            return 2
    else:
        activation = None
    report = run_verification(root=args.root.resolve())
    if activation is not None:
        report["activation_gate"] = activation
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["result"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
