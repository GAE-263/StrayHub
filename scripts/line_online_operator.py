"""Protected VM operator for hashed reviewed plans. Never edits identities/roles.

Preparation is read-only externally. Execution accepts fresh workflow context
over stdin, never secrets on command lines. Private plans remain on the VM.
"""

from __future__ import annotations

import argparse
import fcntl
import grp
import hashlib
import http.client
import json
import os
import pwd
import re
import signal
import stat
import subprocess
import sys
from contextlib import ExitStack, nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.line_menu_manifest import canonical_json, load_publication_manifest
from scripts.line_menu_rollout import LineClient, apply_plan, plan_switches, restoration_plan
from scripts.line_rollout_config import unique, validate_rollout
from scripts.manual_release_gate import validate_manual_run_identity
from scripts.production_config_sync import _safe_file, atomic_write
from scripts.production_config_sync import parser as sync_parser
from scripts.production_config_sync import run as sync
from scripts.release_head_gate import validate_release_head_response

STATE = Path("/var/lib/strayhub/line-rollout")
CURRENT = Path("/opt/strayhub/current")
CONFIG = Path("/etc/strayhub/production.env")
SECRETS = Path("/var/lib/strayhub/secrets")
OPERATIONS = {"config-sync", "reload-config", "menu-switch", "menu-restore"}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def protected(path: Path) -> bytes:
    _safe_file(path, production=True)
    if path.stat().st_size > 1_000_000:
        raise ValueError("input_size")
    return path.read_bytes()


def document(path: Path) -> dict:
    value = json.loads(protected(path), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("input_object")
    return value


def state_file(kind: str, checksum: str) -> Path:
    if kind not in {"plans", "manifests", "receipts", "requests"} or not re.fullmatch(
        r"[0-9a-f]{64}", checksum
    ):
        raise ValueError("state_identity")
    return STATE / kind / (checksum + ".json")


def write_new(path: Path, value: dict) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("immutable_state_exists")
    atomic_write(path, canonical_json(value), uid=0, gid=0, mode=0o600)


def setup_state() -> None:
    if os.geteuid() != 0:
        raise ValueError("root_operator_required")
    for path in (STATE, *(STATE / name for name in ("plans", "manifests", "receipts", "requests"))):
        path.mkdir(mode=0o700, exist_ok=True)
        details = path.lstat()
        if path.is_symlink() or details.st_uid != 0 or details.st_mode & 0o077:
            raise ValueError("private_state_permissions")


def deployed_sha() -> str:
    value = protected(CURRENT / "revision").decode().strip()
    if (
        not re.fullmatch(r"[0-9a-f]{40}", value)
        or document(CURRENT / "release-manifest.json").get("git_sha") != value
    ):
        raise ValueError("deployed_identity")
    return value


def _runtime_secret_bytes() -> bytes:
    """Pin the service-owned generation with no-follow directory descriptors."""
    uid = pwd.getpwnam("strayhub").pw_uid
    gid = grp.getgrnam("strayhub").gr_gid
    with ExitStack() as stack:

        def open_checked(name, *, parent=None, directory=False):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if directory:
                flags |= os.O_DIRECTORY
            fd = os.open(name, flags, dir_fd=parent)
            stack.callback(os.close, fd)
            details = os.fstat(fd)
            expected_mode = 0o700 if directory else 0o600
            expected_type = stat.S_ISDIR if directory else stat.S_ISREG
            if (
                not expected_type(details.st_mode)
                or details.st_uid != uid
                or details.st_gid != gid
                or stat.S_IMODE(details.st_mode) != expected_mode
                or (not directory and (details.st_nlink != 1 or details.st_size > 1_000_000))
            ):
                raise ValueError("credential_unavailable")
            return fd

        root = open_checked(SECRETS, directory=True)
        target = os.readlink("current", dir_fd=root)
        if not re.fullmatch(r"generations/[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}", target):
            raise ValueError("credential_unavailable")
        generations = open_checked("generations", parent=root, directory=True)
        generation = open_checked(target.split("/")[1], parent=generations, directory=True)
        fd = open_checked("runtime.env", parent=generation)
        # A separate duplicated descriptor is closed by the file wrapper.
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError("credential_unavailable")
        return raw


def _runtime_token(raw: bytes) -> str:
    """Decode only the single-quoted scalar format emitted by fetch-secrets.sh."""
    text = raw.decode("utf-8")
    if "\r" in text or "\x00" in text:
        raise ValueError("credential_unavailable")
    values = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([A-Z][A-Z0-9_]+)='((?:[^'\\]|\\['\\])*)'", line)
        if match is None or match[1] in values:
            raise ValueError("credential_unavailable")
        values[match[1]] = re.sub(r"\\(['\\])", r"\1", match[2])
    token = values["LINE_CHANNEL_ACCESS_TOKEN"]
    if not token or any(ord(c) < 33 or ord(c) > 126 for c in token):
        raise ValueError("credential_unavailable")
    return token


def client() -> LineClient:
    # Never change the root-only policy for plans/config/manifests to read secrets.
    try:
        token = _runtime_token(_runtime_secret_bytes())
    except (OSError, KeyError, ValueError):
        raise ValueError("credential_unavailable") from None
    return LineClient(token)


def authorize(context: dict, plan: dict, checksum: str) -> None:
    validate_manual_run_identity(context["actor"], context["triggering_actor"], context["attempt"])
    expected = f"LINE ONLINE {plan['operation']} {plan['git_sha']} {checksum}"
    if (
        context["repository"] != "GAE-263/StrayHub"
        or context["event"] != "workflow_dispatch"
        or context["ref"] != "refs/heads/release"
        or context["confirmation"] != expected
        or context["sha"] != plan["git_sha"]
        or deployed_sha() != plan["git_sha"]
    ):
        raise ValueError("workflow_identity")
    connection = http.client.HTTPSConnection("api.github.com", timeout=15)
    try:
        connection.request(
            "GET",
            "/repos/GAE-263/StrayHub/git/ref/heads/release",
            headers={
                "Authorization": "Bearer " + context["github_token"],
                "User-Agent": "StrayHub-release-readback",
            },
        )
        response = connection.getresponse()
        raw = response.read(100_001)
        if response.status != 200 or len(raw) > 100_000:
            raise ValueError("release_readback")
        validate_release_head_response(raw, plan["git_sha"], context["sha"], deployed_sha())
    finally:
        connection.close()


def manifest_for(checksum: str, git_sha: str):
    path = state_file("manifests", checksum)
    if sha(protected(path)) != checksum:
        raise ValueError("manifest_checksum")
    return load_publication_manifest(
        path, expected_git_sha=git_sha, expected_bot_basic_id="@356imngb"
    )


def prepare(operation: str, request: dict, manifest_sha256: str) -> dict:
    git_sha = deployed_sha()
    manifest = manifest_for(manifest_sha256, git_sha)
    if operation == "config-sync":
        validate_rollout(request, manifest, production=True)
        request = {"rollout": request, "config_sha256": sha(protected(CONFIG))}
    elif operation == "reload-config":
        if request:
            raise ValueError("reload_request_fields")
        request = {
            "config_sha256": sha(protected(CONFIG)),
            "images_sha256": sha(protected(CURRENT / "image-digests.env")),
        }
    elif operation == "menu-switch":
        if set(request) != {"intents", "authorization_source"}:
            raise ValueError("switch_request_fields")
        request = plan_switches(
            client(), manifest, request["intents"], source=request["authorization_source"]
        )
    elif operation == "menu-restore":
        if set(request) != {"original_plan_sha256"}:
            raise ValueError("restore_request_fields")
        original_hash = request["original_plan_sha256"]
        original = document(state_file("plans", original_hash))
        receipt = document(state_file("receipts", original_hash))
        if sha(canonical_json(original)) != original_hash or original["operation"] != "menu-switch":
            raise ValueError("restore_identity")
        request = restoration_plan(client(), manifest, original["request"], receipt)
    else:
        raise ValueError("operation")
    return {
        "schema_version": 1,
        "operation": operation,
        "git_sha": git_sha,
        "manifest_sha256": manifest_sha256,
        "created_at": datetime.now(UTC).isoformat(),
        "config_sha256": sha(protected(CONFIG)),
        "request": request,
    }


def assert_menu_scope(plan: dict) -> None:
    values = {}
    for line in protected(CONFIG).decode().splitlines():
        key, sep, value = line.partition("=")
        if sep:
            if key in values:
                raise ValueError("duplicate_config")
            values[key] = value
    if values.get("LINE_STAFF_MENU_ENABLED", "false") != "false":
        raise ValueError("staff_out_of_scope")
    if plan["operation"] == "menu-restore":
        return
    # Updating production.env alone does not prove a running API adopted it.
    ids = subprocess.run(
        [
            "docker",
            "ps",
            "-q",
            "--filter",
            "label=com.docker.compose.project=strayhub-production",
            "--filter",
            "label=com.docker.compose.service=api",
        ],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.split()
    if len(ids) != 1 or not re.fullmatch(r"[0-9a-f]{12,64}", ids[0]):
        raise ValueError("runtime_api_identity")
    inspected = subprocess.run(["docker", "inspect", ids[0]], capture_output=True, check=True)
    runtime = json.loads(inspected.stdout)[0]
    environment = dict(item.split("=", 1) for item in runtime["Config"]["Env"])
    checked = {
        "LINE_ROLE_MENU_FEATURES_ENABLED",
        "LINE_ROLE_MENU_TEST_ENABLED",
        "LINE_STAFF_MENU_ENABLED",
        "LINE_ROLE_MENU_TEST_CHANNEL_ID",
        "LINE_ROLE_MENU_BOT_SHA256",
        "LINE_CHANNEL_ID",
        "LINE_ROLE_MENU_TEST_USER_SHA256",
        "LINE_ROLE_MENU_TEST_EXPIRES_AT",
        "LINE_RICH_MENU_DEFAULT_ID",
        "LINE_RICH_MENU_VOLUNTEER_ID",
        "LINE_RICH_MENU_ADOPTION_HUB_ID",
        "LINE_ROLE_MENU_REPORT_SHA256",
        "CELERY_AI_ENABLED",
        "GEMINI_MODEL_NAME",
        "GEMINI_USE_RUNTIME_IDENTITY",
        "GEMINI_VERTEX_PROJECT",
        "GEMINI_RUNTIME_SERVICE_ACCOUNT",
    }
    if any(
        environment.get(key, "false" if key == "GEMINI_USE_RUNTIME_IDENTITY" else "")
        != values.get(key, "false" if key == "GEMINI_USE_RUNTIME_IDENTITY" else "")
        for key in checked
    ):
        raise ValueError("runtime_config_not_loaded")
    if runtime["State"].get("Health", {}).get("Status") != "healthy":
        raise ValueError("runtime_unhealthy")
    release = document(CURRENT / "release-manifest.json")
    image = release["images"]["api"]
    if runtime["Config"]["Image"] != image["repository"] + "@" + image["digest"]:
        raise ValueError("runtime_image_mismatch")
    if values.get("LINE_ROLE_MENU_FEATURES_ENABLED") == "true":
        if (
            sha(protected(Path(values["LINE_ROLE_MENU_REPORT_PATH"])))
            != values["LINE_ROLE_MENU_REPORT_SHA256"]
        ):
            raise ValueError("runtime_evidence_changed")
        return
    from datetime import UTC, datetime

    if values.get("LINE_ROLE_MENU_TEST_ENABLED") != "true" or datetime.fromisoformat(
        values["LINE_ROLE_MENU_TEST_EXPIRES_AT"]
    ) <= datetime.now(UTC):
        raise ValueError("scope_inactive")
    hashes = values["LINE_ROLE_MENU_TEST_USER_SHA256"].split(",")
    if any(
        entry["target"] == "default" or sha(entry["target"].encode()) not in hashes
        for entry in plan["request"]["entries"]
    ):
        raise ValueError("outside_scope")


def execute(plan: dict, checksum: str, context: dict) -> dict:
    if (
        set(plan)
        != {
            "schema_version",
            "operation",
            "git_sha",
            "manifest_sha256",
            "request",
            "created_at",
            "config_sha256",
        }
        or plan["schema_version"] != 1
        or plan["operation"] not in OPERATIONS
    ):
        raise ValueError("plan_schema")
    if sha(canonical_json(plan)) != checksum:
        raise ValueError("plan_checksum")
    authorize(context, plan, checksum)  # Before credential file access and preflight.
    age = datetime.now(UTC) - datetime.fromisoformat(plan["created_at"])
    if not timedelta(0) <= age <= timedelta(hours=24):
        raise ValueError("plan_expired")
    if plan["config_sha256"] != sha(protected(CONFIG)):
        raise ValueError("config_drift")
    manifest = manifest_for(plan["manifest_sha256"], plan["git_sha"])
    receipt = state_file("receipts", checksum)
    if receipt.exists():
        raise ValueError("receipt_exists_readback_and_replan")
    request = plan["request"]
    if plan["operation"].startswith("menu-"):
        if plan["operation"] == "menu-switch":
            subprocess.run(
                [
                    str(CURRENT / "infra/gce/scripts/production-preflight.sh"),
                    "--config-env",
                    str(CONFIG),
                    "--image-env",
                    str(CURRENT / "image-digests.env"),
                    "--secrets-root",
                    str(SECRETS),
                ],
                capture_output=True,
                check=True,
            )
        assert_menu_scope(plan)

        def fresh() -> None:
            authorize(context, plan, checksum)
            if plan["config_sha256"] != sha(protected(CONFIG)):
                raise ValueError("config_drift")
            assert_menu_scope(plan)

        return apply_plan(
            client(), manifest, request, receipt=receipt, authorize=fresh, uid=0, gid=0
        )
    if request["config_sha256"] != sha(protected(CONFIG)):
        raise ValueError("config_drift")
    if plan["operation"] == "config-sync":
        rollout_path = state_file("requests", sha(canonical_json(request["rollout"])))
        if not rollout_path.exists():
            write_new(rollout_path, request["rollout"])
        elif protected(rollout_path) != canonical_json(request["rollout"]):
            raise ValueError("rollout_checksum")
        authorize(context, plan, checksum)
        args = sync_parser().parse_args(
            [
                "--manifest",
                str(state_file("manifests", plan["manifest_sha256"])),
                "--expected-manifest-git-sha",
                plan["git_sha"],
                "--expected-bot",
                manifest.bot_basic_id,
                "--application-release-manifest",
                str(CURRENT / "release-manifest.json"),
                "--application-git-sha",
                plan["git_sha"],
                "--config-env",
                str(CONFIG),
                "--image-env",
                str(CURRENT / "image-digests.env"),
                "--secrets-root",
                str(SECRETS),
                "--receipt",
                str(Path("/var/lib/strayhub/config-sync") / (checksum + ".json")),
                "--rollout",
                str(rollout_path),
                "--expected-config-sha256",
                request["config_sha256"],
            ]
        )
        # Existing lock, backup, preflight, rollback, readback and immutable receipt.
        result = sync(args)
        write_new(receipt, {"status": "success", "plan_sha256": checksum, "result": result})
        return result
    if request["images_sha256"] != sha(protected(CURRENT / "image-digests.env")):
        raise ValueError("images_drift")
    command = [
        "docker",
        "compose",
        "--project-name",
        "strayhub-production",
        "--env-file",
        str(CONFIG),
        "--env-file",
        str(SECRETS / "current/runtime.env"),
        "--env-file",
        str(CURRENT / "image-digests.env"),
        "-f",
        str(CURRENT / "infra/gce/docker-compose.production.yml"),
    ]
    authorize(context, plan, checksum)
    preflight = [
        str(CURRENT / "infra/gce/scripts/production-preflight.sh"),
        "--config-env",
        str(CONFIG),
        "--image-env",
        str(CURRENT / "image-digests.env"),
        "--secrets-root",
        str(SECRETS),
    ]
    subprocess.run(preflight, capture_output=True, check=True)
    authorize(context, plan, checksum)
    write_new(receipt, {"status": "intent-recorded", "plan_sha256": checksum})
    # No build/pull, migration, secret refresh or image change; explicitly separate
    # from config-sync. A failed restart requires readback and a fresh reviewed plan.
    subprocess.run(
        command
        + [
            "up",
            "-d",
            "--no-build",
            "--pull",
            "never",
            "--no-deps",
            "--wait",
            "--wait-timeout",
            "120",
            "api",
            "worker",
            "celery-worker",
            "celery-beat",
        ],
        capture_output=True,
        check=True,
    )
    result = {
        "status": "success",
        "plan_sha256": checksum,
        "config_sha256": request["config_sha256"],
        "images_sha256": request["images_sha256"],
    }
    atomic_write(receipt, canonical_json(result), uid=0, gid=0, mode=0o600)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("prepare")
    plan.add_argument("--operation", required=True, choices=sorted(OPERATIONS))
    plan.add_argument("--request", type=Path, required=True)
    plan.add_argument("--manifest-sha256", required=True)
    apply = commands.add_parser("execute")
    apply.add_argument("--plan-sha256", required=True)
    args = parser.parse_args()
    try:
        setup_state()
        lock_path = STATE / "operator.lock"
        if lock_path.is_symlink():
            raise ValueError("unsafe_lock")
        with lock_path.open("a") as lock:
            os.chmod(lock_path, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.command == "prepare":
                result = prepare(args.operation, document(args.request), args.manifest_sha256)
                checksum = sha(canonical_json(result))
                write_new(state_file("plans", checksum), result)
                print(
                    json.dumps(
                        {
                            "plan_sha256": checksum,
                            "operation": result["operation"],
                            "git_sha": result["git_sha"],
                            "external_writes": 0,
                        }
                    )
                )
            else:

                def interrupted(_number, _frame):
                    raise InterruptedError("operator_interrupted")

                for number in (signal.SIGTERM, signal.SIGINT):
                    signal.signal(number, interrupted)
                context = json.loads(sys.stdin.read(100_001), object_pairs_hook=unique)
                plan_doc = document(state_file("plans", args.plan_sha256))
                # Serialize reload/menu operations with the existing config-sync
                # lock. Config-sync acquires that lock inside its own transaction.
                config_lock = CONFIG.with_name(f".{CONFIG.name}.config-sync.lock")
                if config_lock.is_symlink():
                    raise ValueError("unsafe_config_lock")
                manager = (
                    nullcontext()
                    if plan_doc["operation"] == "config-sync"
                    else config_lock.open("a")
                )
                with manager as handle:
                    if handle is not None:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    result = execute(plan_doc, args.plan_sha256, context)
                print(json.dumps({"plan_sha256": args.plan_sha256, "status": result["status"]}))
    except (
        ValueError,
        RuntimeError,
        OSError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
        http.client.HTTPException,
    ):
        parser.exit(1, "online_operation_stopped_readback_required (values suppressed)\n")


if __name__ == "__main__":
    main()
