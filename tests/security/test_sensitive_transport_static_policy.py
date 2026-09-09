from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/security/fixtures/static-policy"
CHECKER = ROOT / "scripts/check_sensitive_transport_policy.py"


def _run_fixture(name: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(ROOT), "--fixture", str(FIXTURES / name)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    ("fixture", "rule"),
    [
        ("negative-unsafe-form.tsx", "ST001"),
        ("negative-hardcoded-password.tsx", "ST002"),
        ("negative-class-a-url.ts", "ST003"),
        ("negative-class-a-query-reader.ts", "ST003"),
        ("negative-unsafe-nginx.conf", "ST004"),
        ("negative-catchall-nginx.conf", "ST005"),
    ],
)
def test_each_negative_fixture_triggers_only_its_expected_rule(fixture: str, rule: str) -> None:
    result = _run_fixture(fixture)
    assert result.returncode == 1
    assert f"[{rule}]" in result.stderr
    for other in {"ST001", "ST002", "ST003", "ST004", "ST005"} - {rule}:
        assert f"[{other}]" not in result.stderr
    assert "fixture-demo-password" not in result.stderr


def test_positive_fixture_preserves_ordinary_and_registered_class_b_query() -> None:
    result = _run_fixture("positive-safe.tsx")
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout


def test_repository_passes_scoped_sensitive_transport_policy() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(ROOT)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Sensitive transport policy: PASS" in result.stdout
