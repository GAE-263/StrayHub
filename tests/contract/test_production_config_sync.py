from __future__ import annotations

import fcntl
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.production_config_sync import MANAGED_KEYS, render_config

from tests.unit.test_line_menu_manifest import BOT, GIT_SHA, manifest_document, write_manifest

APP_SHA = "c" * 40
SECRET_VALUE = "synthetic-secret-value-that-must-remain-private"


def prepare(tmp_path: Path, *, preflight_exit: int = 0, signal_parent: bool = False):
    root = tmp_path / "config-sync"
    root.mkdir(mode=0o700, parents=True)
    config = root / "production.env"
    config.write_text(
        "# retained comment\n"
        "LINE_CHANNEL_ACCESS_TOKEN=" + SECRET_VALUE + "\n"
        "UNMANAGED_VALUE=keep-me\n"
        "LINE_RICH_MENU_DEFAULT_ID=richmenu-old\n"
        "LINE_ROLE_MENU_FEATURES_ENABLED=true\n",
        encoding="utf-8",
    )
    config.chmod(0o600)
    manifest = write_manifest(root / "menus.json", manifest_document())
    release = root / "release.json"
    release.write_text(json.dumps({"git_sha": APP_SHA}), encoding="utf-8")
    image_env = root / "image.env"
    image_env.write_text("STRAYHUB_API_IMAGE=synthetic\n", encoding="utf-8")
    secrets_root = root / "secrets"
    secrets_root.mkdir()
    preflight = root / "preflight.sh"
    body = "#!/usr/bin/env bash\nset -eu\n"
    if signal_parent:
        body += 'kill -TERM "$PPID"\nsleep 2\n'
    else:
        body += f"exit {preflight_exit}\n"
    preflight.write_text(body, encoding="utf-8")
    preflight.chmod(0o700)
    receipt = root / "receipt.json"
    command = [
        sys.executable,
        "-m",
        "scripts.production_config_sync",
        "--manifest",
        str(manifest),
        "--expected-manifest-git-sha",
        GIT_SHA,
        "--expected-bot",
        BOT,
        "--application-release-manifest",
        str(release),
        "--application-git-sha",
        APP_SHA,
        "--config-env",
        str(config),
        "--image-env",
        str(image_env),
        "--secrets-root",
        str(secrets_root),
        "--receipt",
        str(receipt),
        "--test-root",
        str(root),
        "--preflight-script",
        str(preflight),
    ]
    return root, config, receipt, command


def execute(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=10)


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rollout_command(tmp_path, *, preflight_exit=0):
    from datetime import UTC, datetime, timedelta

    root, config, receipt, command = prepare(tmp_path, preflight_exit=preflight_exit)
    (root / "release.json").write_text(json.dumps({"git_sha": GIT_SHA}))
    command[command.index("--application-git-sha") + 1] = GIT_SHA
    rollout = root / "rollout.json"
    rollout.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "bounded",
                "git_sha": GIT_SHA,
                "manifest_sha256": checksum(root / "menus.json"),
                "channel_id": "1234567890",
                "user_sha256": ["a" * 64],
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            }
        )
    )
    rollout.chmod(0o600)
    command += ["--rollout", str(rollout), "--expected-config-sha256", checksum(config)]
    return root, config, receipt, command


def test_rollout_dry_run_zero_write_and_success_receipt(tmp_path):
    root, config, receipt, command = rollout_command(tmp_path)
    before = config.read_bytes()
    result = execute(command + ["--dry-run"])
    assert result.returncode == 0, result.stderr
    assert config.read_bytes() == before and not receipt.exists()
    assert json.loads(result.stdout)["rollout_mode"] == "reviewed"
    result = execute(command)
    assert result.returncode == 0, result.stderr
    assert "LINE_ROLE_MENU_TEST_ENABLED=true" in config.read_text()
    assert "LINE_ROLE_MENU_FEATURES_ENABLED=false" in config.read_text()
    assert SECRET_VALUE not in result.stdout + result.stderr
    assert json.loads(receipt.read_text())["rollout_flags"]["LINE_ROLE_MENU_TEST_ENABLED"] == "true"


def test_rollout_preflight_failure_restores_original_checksum(tmp_path):
    root, config, receipt, command = rollout_command(tmp_path, preflight_exit=1)
    before = config.read_bytes()
    result = execute(command)
    assert result.returncode != 0
    assert config.read_bytes() == before
    assert json.loads(receipt.read_text())["rollback_performed"] is True


def test_rollout_plan_config_drift_or_repeat_never_mutates(tmp_path):
    root, config, receipt, command = rollout_command(tmp_path)
    before = config.read_bytes()
    config.write_bytes(before + b"OTHER_CHANGE=keep\n")
    result = execute(command)
    assert result.returncode != 0
    assert config.read_bytes() == before + b"OTHER_CHANGE=keep\n"
    assert not receipt.exists()
    config.write_bytes(before)
    receipt.write_text('{"existing":"receipt"}')
    result = execute(command)
    assert result.returncode != 0
    assert config.read_bytes() == before
    assert receipt.read_text() == '{"existing":"receipt"}'


def test_render_only_updates_allowlist_and_never_executes_values(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    original = (
        f"DANGEROUS=$(touch {marker})\n"
        f"LINE_CHANNEL_ACCESS_TOKEN={SECRET_VALUE}\n"
        "LINE_RICH_MENU_DEFAULT_ID=richmenu-old\n"
    ).encode()
    manifest = write_manifest(tmp_path / "menus.json", manifest_document())
    from scripts.line_menu_manifest import load_publication_manifest

    verified = load_publication_manifest(
        manifest, expected_git_sha=GIT_SHA, expected_bot_basic_id=BOT
    )
    rendered = render_config(original, verified).decode()

    assert not marker.exists()
    assert f"DANGEROUS=$(touch {marker})" in rendered
    assert f"LINE_CHANNEL_ACCESS_TOKEN={SECRET_VALUE}" in rendered
    assert all(rendered.count(f"{key}=") == 1 for key in MANAGED_KEYS)
    assert all(f"{key}=false" in rendered for key in MANAGED_KEYS[-3:])


def test_duplicate_managed_key_and_malformed_syntax_fail_closed(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path / "menus.json", manifest_document())
    from scripts.line_menu_manifest import load_publication_manifest
    from scripts.production_config_sync import ConfigSyncError

    verified = load_publication_manifest(
        manifest, expected_git_sha=GIT_SHA, expected_bot_basic_id=BOT
    )
    with pytest.raises(ConfigSyncError, match="duplicate managed key"):
        render_config(
            b"LINE_ROLE_MENU_TEST_ENABLED=false\nLINE_ROLE_MENU_TEST_ENABLED=true\n",
            verified,
        )
    with pytest.raises(ConfigSyncError, match="malformed syntax"):
        render_config(b"export UNSAFE=value\n", verified)


def test_dry_run_has_no_writes_backup_receipt_or_preflight(tmp_path: Path) -> None:
    root, config, receipt, command = prepare(tmp_path, preflight_exit=99)
    before = checksum(config)

    result = execute([*command, "--dry-run"])

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["rollout_mode"] == "inert"
    assert output["managed_keys"] == list(MANAGED_KEYS)
    assert checksum(config) == before
    assert not receipt.exists()
    assert not list(root.glob("*.config-sync-backup.*"))
    assert not (root / ".production.env.config-sync.lock").exists()
    assert SECRET_VALUE not in result.stdout + result.stderr


def test_success_is_atomic_preserves_secrets_and_writes_safe_receipt(tmp_path: Path) -> None:
    root, config, receipt, command = prepare(tmp_path)
    previous = checksum(config)

    result = execute(command)

    assert result.returncode == 0, result.stderr
    rendered = config.read_text()
    assert f"LINE_CHANNEL_ACCESS_TOKEN={SECRET_VALUE}" in rendered
    assert "UNMANAGED_VALUE=keep-me" in rendered
    assert all(f"{key}=false" in rendered for key in MANAGED_KEYS[-3:])
    assert config.stat().st_mode & 0o777 == 0o640
    backups = list(root.glob(".production.env.config-sync-backup.*"))
    assert len(backups) == 1 and backups[0].stat().st_mode & 0o777 == 0o640
    assert not list(root.glob(".production.env.tmp.*"))
    with (root / ".production.env.config-sync.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    payload = json.loads(receipt.read_text())
    assert payload["status"] == "success" and payload["preflight"] == "passed"
    assert payload["previous_config_sha256"] == previous
    assert payload["resulting_config_sha256"] == checksum(config)
    assert payload["rollback_performed"] is False
    assert SECRET_VALUE not in receipt.read_text() + result.stdout + result.stderr


def test_preflight_failure_restores_original_checksum_and_records_failure(tmp_path: Path) -> None:
    _root, config, receipt, command = prepare(tmp_path, preflight_exit=23)
    original = config.read_bytes()

    result = execute(command)

    assert result.returncode != 0
    assert config.read_bytes() == original
    payload = json.loads(receipt.read_text())
    assert payload["status"] == "failed"
    assert payload["failure_gate"] == "preflight"
    assert payload["rollback_performed"] is True
    assert payload["previous_config_sha256"] == checksum(config)
    assert SECRET_VALUE not in receipt.read_text() + result.stdout + result.stderr


def test_noop_is_idempotent_runs_preflight_without_backup(tmp_path: Path) -> None:
    root, config, receipt, command = prepare(tmp_path)
    first = execute(command)
    assert first.returncode == 0
    first_content = config.read_bytes()
    first_backups = list(root.glob(".production.env.config-sync-backup.*"))
    receipt.unlink()

    second = execute(command)

    assert second.returncode == 0
    payload = json.loads(receipt.read_text())
    assert payload["changed"] is False and payload["preflight"] == "passed"
    assert config.read_bytes() == first_content
    assert list(root.glob(".production.env.config-sync-backup.*")) == first_backups


def test_lock_contention_fails_without_modifying_config(tmp_path: Path) -> None:
    root, config, receipt, command = prepare(tmp_path)
    original = config.read_bytes()
    lock_path = root / ".production.env.config-sync.lock"
    lock_path.touch(mode=0o600)
    with lock_path.open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = execute(command)

    assert result.returncode != 0 and '"failure_gate": "lock"' in result.stderr
    assert config.read_bytes() == original
    assert json.loads(receipt.read_text())["failure_gate"] == "lock"


def test_signal_during_preflight_rolls_back_without_half_config(tmp_path: Path) -> None:
    _root, config, receipt, command = prepare(tmp_path, signal_parent=True)
    original = config.read_bytes()

    result = execute(command)

    assert result.returncode != 0
    assert config.read_bytes() == original
    payload = json.loads(receipt.read_text())
    assert payload["failure_gate"] == "interrupted"
    assert payload["rollback_performed"] is True


def test_symlink_target_and_path_escape_are_rejected(tmp_path: Path) -> None:
    root, config, _receipt, command = prepare(tmp_path)
    real = root / "real.env"
    config.rename(real)
    config.symlink_to(real)
    result = execute(command)
    assert result.returncode != 0 and '"failure_gate": "filesystem"' in result.stderr
    assert real.read_text().startswith("# retained comment")

    root, _config, _receipt, command = prepare(tmp_path / "second")
    command[command.index("--receipt") + 1] = str(tmp_path / "escaped.json")
    result = execute(command)
    assert result.returncode != 0 and "escapes" in result.stderr


def test_unsafe_config_mode_is_rejected(tmp_path: Path) -> None:
    _root, config, receipt, command = prepare(tmp_path)
    config.chmod(0o666)

    result = execute(command)

    assert result.returncode != 0 and "group/world writable" in result.stderr
    assert not receipt.exists()


def test_application_and_menu_identity_mismatch_stop_before_write(tmp_path: Path) -> None:
    _root, config, receipt, command = prepare(tmp_path)
    original = config.read_bytes()
    command[command.index("--application-git-sha") + 1] = "d" * 40

    result = execute(command)

    assert result.returncode != 0 and '"failure_gate": "application_manifest"' in result.stderr
    assert config.read_bytes() == original and not receipt.exists()


def test_shell_wrapper_is_inert_and_does_not_manage_services() -> None:
    source = Path("infra/gce/scripts/sync-production-config.sh").read_text()
    assert "scripts.production_config_sync" in source
    for forbidden in ("systemctl", "docker", "service ", "LINE_CHANNEL_ACCESS_TOKEN"):
        assert forbidden not in source


def test_rollback_keeps_exclusive_lock_until_failure_receipt(tmp_path, monkeypatch):
    from scripts import production_config_sync as sync

    root, config, receipt, command = prepare(tmp_path, preflight_exit=23)
    args = sync.parser().parse_args(command[3:])
    original = config.read_bytes()
    real_write = sync.atomic_write
    checked = []

    def guarded_write(path, content, **kwargs):
        if (path == config and content == original) or path == receipt:
            with (root / ".production.env.config-sync.lock").open("rb") as contender:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            checked.append(path)
        return real_write(path, content, **kwargs)

    monkeypatch.setattr(sync, "atomic_write", guarded_write)
    with pytest.raises(sync.ConfigSyncError, match="preflight failed"):
        sync.run(args)
    assert checked == [config, receipt]
    assert config.read_bytes() == original
    with (root / ".production.env.config-sync.lock").open("rb") as released:
        fcntl.flock(released, fcntl.LOCK_EX | fcntl.LOCK_NB)
