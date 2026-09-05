from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from scripts.verify_demo_data import build_synthetic_data_evidence
from scripts.verify_sensitive_transport_runtime import (
    ActivationEvidenceError,
    verify_activation_evidence,
)

ORIGIN = "https://reserved-example.ngrok.app"
REQUIRED_CHECKS = (
    "exact_runtime_reserved_host_validated",
    "synthetic_demo_data_verified",
    "old_demo_password_rejected",
    "new_demo_password_accepted",
    "old_demo_sessions_revoked",
    "allow_and_deny_route_matrix_passed",
    "sensitive_log_sentinel_absent",
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _write_evidence(
    path: Path,
    *,
    evidence_kind: str = "manual_external",
    origin: str = ORIGIN,
) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "evidence_kind": evidence_kind,
                "runtime_origin": origin,
                "environment": "synthetic-demo",
                "operator": "authorized-operator",
                "recorded_at_utc": "2026-09-05T00:00:00Z",
                "checks": {
                    name: {
                        "result": "PASS",
                        "evidence_digest_sha256": _digest(name),
                    }
                    for name in REQUIRED_CHECKS
                },
            }
        ),
        encoding="utf-8",
    )


def test_manual_external_evidence_opens_exact_reserved_origin(tmp_path: Path) -> None:
    evidence = tmp_path / "activation.json"
    _write_evidence(evidence)

    result = verify_activation_evidence(evidence, expected_origin=ORIGIN)

    assert result["status"] == "PASS"
    assert result["evidence_kind"] == "manual_external"
    assert result["runtime_origin_digest"] == _digest(ORIGIN)[:16]
    assert ORIGIN not in json.dumps(result)


@pytest.mark.parametrize("missing", REQUIRED_CHECKS)
def test_missing_or_failed_required_evidence_fails_closed(tmp_path: Path, missing: str) -> None:
    evidence = tmp_path / "activation.json"
    _write_evidence(evidence)
    payload = json.loads(evidence.read_text())
    payload["checks"][missing]["result"] = "BLOCKED"
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ActivationEvidenceError, match="activation evidence is incomplete"):
        verify_activation_evidence(evidence, expected_origin=ORIGIN)


def test_boolean_attestation_and_wrong_origin_are_rejected(tmp_path: Path) -> None:
    evidence = tmp_path / "activation.json"
    evidence.write_text(json.dumps({"t008_complete": True}), encoding="utf-8")
    with pytest.raises(ActivationEvidenceError, match="schema"):
        verify_activation_evidence(evidence, expected_origin=ORIGIN)

    _write_evidence(evidence, origin="https://other-example.ngrok.app")
    with pytest.raises(ActivationEvidenceError, match="runtime origin"):
        verify_activation_evidence(evidence, expected_origin=ORIGIN)

    _write_evidence(evidence, origin="http://127.0.0.1:8082")
    with pytest.raises(ActivationEvidenceError, match="runtime origin"):
        verify_activation_evidence(evidence, expected_origin="http://127.0.0.1:8082")


def test_synthetic_fixture_never_satisfies_public_activation(tmp_path: Path) -> None:
    evidence = tmp_path / "activation.json"
    _write_evidence(evidence, evidence_kind="synthetic_local")

    with pytest.raises(ActivationEvidenceError, match="manual external"):
        verify_activation_evidence(evidence, expected_origin=ORIGIN)

    result = verify_activation_evidence(
        evidence,
        expected_origin=ORIGIN,
        allow_synthetic=True,
    )
    assert result["status"] == "PASS_SYNTHETIC_ONLY"


def test_evidence_cannot_contain_secret_bearing_fields(tmp_path: Path) -> None:
    evidence = tmp_path / "activation.json"
    _write_evidence(evidence)
    payload = json.loads(evidence.read_text())
    payload["password"] = "must-never-be-persisted"
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ActivationEvidenceError, match="sensitive field"):
        verify_activation_evidence(evidence, expected_origin=ORIGIN)


def test_synthetic_demo_inventory_evidence_is_bounded_and_secret_free() -> None:
    results = {
        code: {"animals": 1, "valid": True, "photos_checked": False}
        for code in ("FURKIDS-ASIA", "MOA-SHELTER-51", "MOA-SHELTER-58")
    }
    evidence = build_synthetic_data_evidence(results)
    assert evidence["classification"] == "synthetic_local_demo"
    assert evidence["organization_count"] == 3
    assert len(str(evidence["inventory_digest_sha256"])) == 64

    with pytest.raises(RuntimeError, match="not_verified"):
        build_synthetic_data_evidence({"UNKNOWN": {"valid": True}})
