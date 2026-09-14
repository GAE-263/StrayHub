"""Fail-closed LINE menu manifest to production configuration synchronization."""

from __future__ import annotations

import argparse
import fcntl
import grp
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.line_menu_manifest import (
    GIT_SHA,
    MenuManifestError,
    VerifiedMenuManifest,
    load_publication_manifest,
)

MANAGED_KEYS = (
    "LINE_RICH_MENU_DEFAULT_ID",
    "LINE_RICH_MENU_VOLUNTEER_ID",
    "LINE_RICH_MENU_ADOPTION_HUB_ID",
    "LINE_ROLE_MENU_FEATURES_ENABLED",
    "LINE_ROLE_MENU_TEST_ENABLED",
    "LINE_STAFF_MENU_ENABLED",
)
ROLLOUT_FLAGS = {
    "LINE_ROLE_MENU_FEATURES_ENABLED": "false",
    "LINE_ROLE_MENU_TEST_ENABLED": "false",
    "LINE_STAFF_MENU_ENABLED": "false",
}
ENV_LINE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)")


class ConfigSyncError(RuntimeError):
    def __init__(self, gate: str, message: str):
        super().__init__(message)
        self.gate = gate


class SyncInterrupted(ConfigSyncError):
    def __init__(self) -> None:
        super().__init__("interrupted", "configuration sync interrupted")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConfigSyncError("application_manifest", f"duplicate JSON key: {key}")
        result[key] = value
    return result


def application_identity(path: Path, expected_sha: str) -> str:
    if not GIT_SHA.fullmatch(expected_sha):
        raise ConfigSyncError("application_manifest", "application Git SHA is invalid")
    try:
        data = json.loads(path.read_bytes(), object_pairs_hook=_duplicate_json_keys)
    except ConfigSyncError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigSyncError(
            "application_manifest", "unable to parse application release manifest"
        ) from exc
    if not isinstance(data, dict) or data.get("git_sha") != expected_sha:
        raise ConfigSyncError("application_manifest", "application release identity mismatch")
    return expected_sha


def render_config(original: bytes, manifest: VerifiedMenuManifest) -> bytes:
    try:
        text = original.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigSyncError("config_parse", "production config must be UTF-8") from exc
    if "\x00" in text or "\r" in text:
        raise ConfigSyncError("config_parse", "production config contains unsafe bytes")
    replacements = {
        "LINE_RICH_MENU_DEFAULT_ID": manifest.menus["default"]["id"],
        "LINE_RICH_MENU_VOLUNTEER_ID": manifest.menus["volunteer"]["id"],
        "LINE_RICH_MENU_ADOPTION_HUB_ID": manifest.menus["adoption_hub"]["id"],
        **ROLLOUT_FLAGS,
    }
    seen: set[str] = set()
    rendered: list[str] = []
    for line in text.splitlines():
        if not line or line.lstrip().startswith("#"):
            rendered.append(line)
            continue
        match = ENV_LINE.fullmatch(line)
        if not match:
            raise ConfigSyncError("config_parse", "production config contains malformed syntax")
        key = match.group(1)
        if key in replacements:
            if key in seen:
                raise ConfigSyncError("config_parse", f"duplicate managed key: {key}")
            seen.add(key)
            rendered.append(f"{key}={replacements[key]}")
        else:
            rendered.append(line)
    for key in MANAGED_KEYS:
        if key not in seen:
            rendered.append(f"{key}={replacements[key]}")
    return ("\n".join(rendered) + "\n").encode()


def _safe_file(path: Path, *, production: bool, config: bool = False) -> os.stat_result:
    try:
        details = path.lstat()
    except OSError as exc:
        raise ConfigSyncError("filesystem", "required protected file is unavailable") from exc
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ConfigSyncError("filesystem", "protected file must be a regular non-symlink")
    mode = stat.S_IMODE(details.st_mode)
    if production:
        expected_gid = grp.getgrnam("strayhub").gr_gid if config else 0
        expected_mode = 0o640 if config else None
        if details.st_uid != 0 or (config and details.st_gid != expected_gid):
            raise ConfigSyncError("filesystem", "protected file owner/group is unsafe")
        if expected_mode is not None and mode != expected_mode:
            raise ConfigSyncError("filesystem", "production config mode must be 0640")
        if mode & 0o022:
            raise ConfigSyncError("filesystem", "protected input is group/world writable")
    elif mode & 0o022:
        raise ConfigSyncError("filesystem", "test protected file is group/world writable")
    return details


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError:
        return False
    return True


def validate_paths(args: argparse.Namespace) -> tuple[bool, int, int]:
    config = Path(args.config_env)
    receipt = Path(args.receipt)
    if args.test_root:
        requested_root = Path(args.test_root)
        if requested_root.is_symlink():
            raise ConfigSyncError("filesystem", "test root must not be a symlink")
        root = requested_root.resolve(strict=True)
        temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
        if not _within(root, temp_root) or root == temp_root or root.is_symlink():
            raise ConfigSyncError("filesystem", "test root must be a dedicated temporary directory")
        paths = (
            config,
            receipt,
            Path(args.manifest),
            Path(args.application_release_manifest),
            Path(args.image_env),
            Path(args.secrets_root),
            Path(args.preflight_script) if args.preflight_script else root,
        )
        if any(not _within(path, root) for path in paths):
            raise ConfigSyncError("filesystem", "test path escapes the dedicated root")
        return False, os.getuid(), os.getgid()
    if os.geteuid() != 0:
        raise ConfigSyncError("filesystem", "production config sync must run as root")
    if config != Path("/etc/strayhub/production.env"):
        raise ConfigSyncError("filesystem", "production target must be canonical production.env")
    if not _within(receipt, Path("/var/lib/strayhub/config-sync")):
        raise ConfigSyncError(
            "filesystem", "receipt must use the canonical config-sync state directory"
        )
    return True, 0, grp.getgrnam("strayhub").gr_gid


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: Path, content: bytes, *, uid: int, gid: int, mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        os.fchown(descriptor, uid, gid)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_receipt(path: Path, payload: dict[str, Any], *, uid: int, gid: int) -> None:
    if path.exists() or path.is_symlink():
        raise ConfigSyncError("receipt", "immutable config-sync receipt already exists")
    if path.parent.exists() and path.parent.is_symlink():
        raise ConfigSyncError("receipt", "config-sync receipt directory is a symlink")
    path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    content = json.dumps(payload, sort_keys=True, indent=2).encode() + b"\n"
    atomic_write(path, content, uid=uid, gid=gid, mode=0o640)


def receipt_payload(
    *,
    status: str,
    gate: str,
    application_git_sha: str,
    manifest: VerifiedMenuManifest,
    previous_sha: str,
    resulting_sha: str,
    changed: bool,
    preflight: str,
    rollback_performed: bool,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "operation": "config-sync",
        "status": status,
        "failure_gate": gate if status == "failed" else None,
        "application_git_sha": application_git_sha,
        "menu_manifest_git_sha": manifest.git_sha,
        "menu_manifest_sha256": manifest.manifest_sha256,
        "bot_basic_id": manifest.bot_basic_id,
        "menus": {role: value["id"] for role, value in manifest.menus.items()},
        "rollout_flags": ROLLOUT_FLAGS,
        "target_config": "production.env",
        "previous_config_sha256": previous_sha,
        "resulting_config_sha256": resulting_sha,
        "changed": changed,
        "preflight": preflight,
        "rollback_performed": rollback_performed,
        "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }


def _signal_handler(_signum: int, _frame: object) -> None:
    raise SyncInterrupted()


def run(args: argparse.Namespace) -> dict[str, Any]:
    production, uid, gid = validate_paths(args)
    config_path = Path(args.config_env)
    receipt_path = Path(args.receipt)
    manifest_path = Path(args.manifest)
    release_manifest_path = Path(args.application_release_manifest)
    image_env = Path(args.image_env)
    secrets_root = Path(args.secrets_root)
    for path in (config_path, manifest_path, release_manifest_path, image_env):
        _safe_file(path, production=production, config=path == config_path)
    if secrets_root.is_symlink() or not secrets_root.is_dir():
        raise ConfigSyncError("filesystem", "secrets root must be a non-symlink directory")
    application_git_sha = application_identity(release_manifest_path, args.application_git_sha)
    try:
        manifest = load_publication_manifest(
            manifest_path,
            expected_git_sha=args.expected_manifest_git_sha,
            expected_bot_basic_id=args.expected_bot,
        )
    except MenuManifestError as exc:
        raise ConfigSyncError("menu_manifest", str(exc)) from exc
    original = config_path.read_bytes()
    rendered = render_config(original, manifest)
    previous_sha = sha256_bytes(original)
    resulting_sha = sha256_bytes(rendered)
    changed = original != rendered
    plan = {
        "application_git_sha": application_git_sha,
        "menu_manifest_git_sha": manifest.git_sha,
        "menu_manifest_sha256": manifest.manifest_sha256,
        "target_config": "production.env",
        "managed_keys": list(MANAGED_KEYS),
        "previous_config_sha256": previous_sha,
        "resulting_config_sha256": resulting_sha,
        "rollout_mode": "inert",
        "changed": changed,
        "validation": "passed",
    }
    if args.dry_run:
        return plan

    lock_path = config_path.with_name(f".{config_path.name}.config-sync.lock")
    if lock_path.is_symlink():
        raise ConfigSyncError("lock", "config-sync lock path is a symlink")
    lock_path.touch(mode=0o640, exist_ok=True)
    os.chown(lock_path, uid, gid)
    os.chmod(lock_path, 0o640)
    replaced = False
    old_handlers = {
        signum: signal.signal(signum, _signal_handler) for signum in (signal.SIGINT, signal.SIGTERM)
    }
    lock = None
    try:
        lock = lock_path.open("rb")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ConfigSyncError("lock", "another config sync holds the lock") from exc
        # Re-read under lock so a concurrent edit cannot be overwritten.
        current = config_path.read_bytes()
        if sha256_bytes(current) != previous_sha:
            raise ConfigSyncError("lock", "production config changed after validation")
        if changed:
            descriptor, _backup_name = tempfile.mkstemp(
                prefix=f".{config_path.name}.config-sync-backup.", dir=config_path.parent
            )
            os.fchmod(descriptor, 0o640)
            os.fchown(descriptor, uid, gid)
            with os.fdopen(descriptor, "wb") as backup:
                backup.write(original)
                backup.flush()
                os.fsync(backup.fileno())
            _fsync_directory(config_path.parent)
            replaced = True
            atomic_write(config_path, rendered, uid=uid, gid=gid, mode=0o640)
        preflight_script = (
            Path(args.preflight_script)
            if args.preflight_script
            else (Path(__file__).resolve().parents[1] / "infra/gce/scripts/production-preflight.sh")
        )
        preflight_details = _safe_file(preflight_script, production=production)
        if not preflight_details.st_mode & stat.S_IXUSR:
            raise ConfigSyncError("preflight", "canonical production preflight is not executable")
        command = [
            str(preflight_script),
            "--config-env",
            str(config_path),
            "--secrets-root",
            str(secrets_root),
            "--project-name",
            "strayhub-d1-preflight-config-sync",
            "--image-env",
            str(image_env),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
        except OSError as exc:
            raise ConfigSyncError("preflight", "canonical production preflight failed") from exc
        if completed.returncode != 0:
            raise ConfigSyncError("preflight", "canonical production preflight failed")
        payload = receipt_payload(
            status="success",
            gate="",
            application_git_sha=application_git_sha,
            manifest=manifest,
            previous_sha=previous_sha,
            resulting_sha=resulting_sha,
            changed=changed,
            preflight="passed",
            rollback_performed=False,
        )
        write_receipt(receipt_path, payload, uid=uid, gid=gid)
        return payload
    except (ConfigSyncError, OSError) as caught:
        sync_error = (
            caught
            if isinstance(caught, ConfigSyncError)
            else ConfigSyncError("filesystem", "atomic filesystem operation failed")
        )
        rolled_back = False
        if replaced:
            try:
                atomic_write(config_path, original, uid=uid, gid=gid, mode=0o640)
            except OSError as rollback_error:
                raise ConfigSyncError("rollback", "original config restoration failed") from (
                    rollback_error
                )
            if sha256_bytes(config_path.read_bytes()) != previous_sha:
                raise ConfigSyncError(
                    "rollback", "original config checksum was not restored"
                ) from sync_error
            rolled_back = True
        failure_receipt = receipt_payload(
            status="failed",
            gate=sync_error.gate,
            application_git_sha=application_git_sha,
            manifest=manifest,
            previous_sha=previous_sha,
            resulting_sha=previous_sha if rolled_back else sha256_bytes(config_path.read_bytes()),
            changed=changed,
            preflight="failed" if sync_error.gate == "preflight" else "not-run",
            rollback_performed=rolled_back,
        )
        try:
            write_receipt(receipt_path, failure_receipt, uid=uid, gid=gid)
        except (ConfigSyncError, OSError):
            pass
        if isinstance(caught, ConfigSyncError):
            raise
        raise sync_error from caught
    finally:
        if lock is not None:
            lock.close()
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--manifest", required=True)
    result.add_argument("--expected-manifest-git-sha", required=True)
    result.add_argument("--expected-bot", required=True)
    result.add_argument("--application-release-manifest", required=True)
    result.add_argument("--application-git-sha", required=True)
    result.add_argument("--config-env", required=True)
    result.add_argument("--image-env", required=True)
    result.add_argument("--secrets-root", required=True)
    result.add_argument("--receipt", required=True)
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--test-root", help=argparse.SUPPRESS)
    result.add_argument("--preflight-script", help=argparse.SUPPRESS)
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        result = run(args)
    except ConfigSyncError as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "operation": "config-sync",
                    "status": "failed",
                    "failure_gate": exc.gate,
                    "message": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
