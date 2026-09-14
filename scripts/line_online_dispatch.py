"""Pass short-lived GitHub readback context on stdin to the protected VM runner."""

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.line_online_gate import authorize
from scripts.manual_release_gate import _load_json


def main() -> None:
    operation = os.environ["ONLINE_OPERATION"]
    checksum = os.environ["PLAN_SHA256"]
    git_sha = os.environ["INPUT_SHA"]
    confirmation = os.environ["CONFIRMATION"]
    # Reuse config validation, do not accept targets from the plan or workflow input.
    import tempfile

    from scripts.manual_release_gate import export_application_config

    with tempfile.TemporaryDirectory(prefix="online-config-") as temporary:
        config_path = Path("infra/gce/application-release-config.json")
        export_application_config(config_path, Path(temporary) / "validated")
        config = _load_json(config_path)
    authorize(operation, checksum, git_sha, confirmation)  # Immediately before SSH/IAP.
    context = {
        "actor": os.environ["GITHUB_ACTOR"],
        "triggering_actor": os.environ["GITHUB_TRIGGERING_ACTOR"],
        "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "repository": os.environ["GITHUB_REPOSITORY"],
        "event": os.environ["GITHUB_EVENT_NAME"],
        "ref": os.environ["GITHUB_REF"],
        "sha": os.environ["GITHUB_SHA"],
        "confirmation": confirmation,
        "github_token": os.environ["GH_TOKEN"],
    }
    command = [
        "gcloud",
        "compute",
        "ssh",
        config["production_instance"],
        "--project",
        config["gcp_project_id"],
        "--zone",
        config["production_zone"],
        "--tunnel-through-iap",
        "--quiet",
        "--command",
        "sudo -n /opt/strayhub/current/infra/gce/scripts/line-online-operator.sh "
        "execute --plan-sha256 " + checksum,
    ]
    result = subprocess.run(
        command, input=json.dumps(context).encode(), capture_output=True, check=False
    )
    if result.returncode != 0:
        sys.exit("online_operator_stopped_readback_required (remote output suppressed)")
    # Do not relay arbitrary remote output or credential-bearing exceptions.
    response = json.loads(result.stdout)
    if response != {"plan_sha256": checksum, "status": "success"}:
        sys.exit("online_operator_readback_invalid")
    print(json.dumps(response))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, KeyError, OSError, subprocess.SubprocessError):
        sys.exit("online_dispatch_denied (values suppressed)")
