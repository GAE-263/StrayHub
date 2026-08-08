from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
QUALITY_TARGETS = (
    "tests/integration/test_empty_database_bootstrap.py",
    "tests/integration/test_database_scope_setter.py",
    "tests/contract/test_authentication_adapters.py",
    "tests/security/test_line_webhook_signature.py",
    "tests/unit/test_line_care_report_state_machine.py",
    "tests/integration/test_media_validation.py",
    "tests/integration/test_ai_job_dispatch_fallback.py",
    "tests/isolation/test_full_cross_tenant_matrix.py",
)


@pytest.mark.quality
def test_feature_quality_matrix_runs_required_local_boundaries() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *QUALITY_TARGETS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )

    assert result.returncode == 0, (
        f"Feature quality matrix failed:\n{result.stdout}\n{result.stderr}"
    )


@pytest.mark.quality
def test_feature_quality_matrix_has_no_unexplained_skip() -> None:
    forbidden = ("pytest.skip(", "pytest.importorskip(", "pytest.mark.skip")
    violations = []
    for path in (ROOT / "tests").rglob("*.py"):
        if path == Path(__file__):
            continue
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in forbidden):
            violations.append(str(path.relative_to(ROOT)))

    assert violations == []
