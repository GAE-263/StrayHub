from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("failures", "status", "message", "expected_calls", "expected_status"),
    [
        (0, 255, "Permission denied (publickey).", 1, 0),
        (2, 255, "Permission denied (publickey).", 3, 0),
        (3, 255, "Permission denied (publickey).", 3, 255),
        (1, 1, "Permission denied (publickey).", 1, 1),
        (1, 255, "Connection refused", 1, 255),
    ],
)
def test_probe_retries_only_publickey_transport_failure(
    tmp_path: Path,
    failures: int,
    status: int,
    message: str,
    expected_calls: int,
    expected_status: int,
) -> None:
    yaml = __import__("yaml")
    document = yaml.load(
        (ROOT / ".github/workflows/gce-release.yml").read_text(), Loader=yaml.BaseLoader
    )
    steps = document["jobs"]["verify-production"]["steps"]
    probe = next(s for s in steps if s.get("name") == "Establish verification SSH transport")
    verification = next(
        s for s in steps if s.get("name") == "Verify exact receipt and runtime over IAP"
    )
    assert steps.index(probe) < steps.index(verification)
    assert "--command true" in probe["run"]
    assert "verify-release-receipt.sh" not in probe["run"]
    assert "for attempt" not in verification["run"]
    mock = tmp_path / "gcloud"
    mock.write_text(
        "#!/bin/bash\n"
        'n=0; [[ ! -f "$CALLS" ]] || read -r n < "$CALLS"\n'
        'n=$((n+1)); echo "$n" > "$CALLS"\n'
        '[[ "${*: -2}" == "--command true" ]] || exit 99\n'
        'if ((n <= FAILURES)); then echo "$MESSAGE" >&2; exit "$STATUS"; fi\n'
    )
    mock.chmod(0o700)
    sleep = tmp_path / "sleep"
    sleep.write_text("#!/bin/bash\nexit 0\n")
    sleep.chmod(0o700)
    calls = tmp_path / "calls"
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", probe["run"]],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "CALLS": str(calls),
            "FAILURES": str(failures),
            "STATUS": str(status),
            "MESSAGE": message,
            "VERIFY_INSTANCE": "synthetic",
            "VERIFY_PROJECT": "synthetic",
            "VERIFY_ZONE": "synthetic",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected_status
    assert int(calls.read_text()) == expected_calls
    assert message not in result.stdout + result.stderr
