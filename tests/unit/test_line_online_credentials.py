"""Synthetic filesystem and credentials only; no LINE/cloud transport."""

import grp
import os
import pwd
from types import SimpleNamespace

import pytest
from scripts import line_online_operator as operator


@pytest.fixture
def secret_tree(tmp_path, monkeypatch):
    root = tmp_path / "secrets"
    generation = root / "generations" / "20260915T010000Z-1234abcd"
    generation.mkdir(parents=True)
    for directory in (root, root / "generations", generation):
        directory.chmod(0o700)
    (root / "current").symlink_to("generations/" + generation.name)
    env = generation / "runtime.env"
    env.write_text("LINE_CHANNEL_ACCESS_TOKEN='synthetic-token'\n")
    env.chmod(0o600)
    monkeypatch.setattr(operator, "SECRETS", root)
    monkeypatch.setattr(pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=os.getuid()))
    monkeypatch.setattr(grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=os.getgid()))
    monkeypatch.setattr(operator, "LineClient", lambda token: token)
    return root, generation, env


def test_service_owned_generation_is_read_without_chown(secret_tree):
    _, _, env = secret_tree
    before = env.stat()
    assert operator.client() == "synthetic-token"
    after = env.stat()
    assert (before.st_uid, before.st_gid, before.st_mode) == (
        after.st_uid,
        after.st_gid,
        after.st_mode,
    )


def test_writer_quotes_are_decoded_before_client(secret_tree, monkeypatch):
    # Isolate the original parser failure from the original root-only reader.
    monkeypatch.setattr(operator, "protected", lambda path: path.read_bytes())
    assert operator.client() == "synthetic-token"


@pytest.mark.parametrize(
    "content",
    [
        "",
        "LINE_CHANNEL_ACCESS_TOKEN=''\n",
        "LINE_CHANNEL_ACCESS_TOKEN=unquoted\n",
        "LINE_CHANNEL_ACCESS_TOKEN='one'\nLINE_CHANNEL_ACCESS_TOKEN='two'\n",
        "LINE_CHANNEL_ACCESS_TOKEN='two words'\n",
        "LINE_CHANNEL_ACCESS_TOKEN='line\nbreak'\n",
        "LINE_CHANNEL_ACCESS_TOKEN='bad\\q'\n",
        "LINE_CHANNEL_ACCESS_TOKEN='unterminated\n",
        "LINE_CHANNEL_ACCESS_TOKEN='value' #comment\n",
        "LINE_CHANNEL_ACCESS_TOKEN='value'\r\n",
    ],
)
def test_invalid_token_file_fails_without_leaking_content(secret_tree, content):
    _, _, env = secret_tree
    env.write_bytes(content.encode())
    with pytest.raises(ValueError) as caught:
        operator.client()
    assert str(caught.value) == "credential_unavailable"


@pytest.mark.parametrize(
    "fault",
    [
        "file_mode",
        "directory_mode",
        "owner",
        "group",
        "file_symlink",
        "generation_symlink",
        "generations_symlink",
        "root_symlink",
        "escape",
        "hardlink",
        "oversized",
    ],
)
def test_unsafe_secret_files_fail_closed(secret_tree, monkeypatch, tmp_path, fault):
    root, generation, env = secret_tree
    if fault == "file_mode":
        env.chmod(0o644)
    elif fault == "directory_mode":
        generation.chmod(0o750)
    elif fault == "owner":
        monkeypatch.setattr(pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=os.getuid() + 1))
    elif fault == "group":
        monkeypatch.setattr(grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=os.getgid() + 1))
    elif fault == "file_symlink":
        target = generation / "other"
        env.rename(target)
        env.symlink_to(target)
    elif fault in {"generation_symlink", "generations_symlink", "root_symlink"}:
        target = {
            "generation_symlink": generation,
            "generations_symlink": root / "generations",
            "root_symlink": root,
        }[fault]
        moved = tmp_path / "moved"
        target.rename(moved)
        target.symlink_to(moved)
    elif fault == "escape":
        (root / "current").unlink()
        (root / "current").symlink_to(generation)
    elif fault == "hardlink":
        os.link(env, generation / "linked")
    elif fault == "oversized":
        env.write_bytes(b"x" * 1_000_001)
    with pytest.raises(ValueError, match="^credential_unavailable$"):
        operator.client()


@pytest.mark.parametrize("token", ["synthetic+/token==", r"synthetic\slash"])
def test_actual_writer_scalar_encoding_roundtrip(secret_tree, token):
    import subprocess
    from pathlib import Path

    # Execute the scalar encoder from the production writer with synthetic values.
    source = Path("infra/gce/scripts/fetch-secrets.sh").read_text()
    start = source.index('  escaped="${value//')
    end = source.index("  unset value escaped", start)
    _, _, env = secret_tree
    env.write_bytes(b"")
    subprocess.run(
        [
            "bash",
            "-c",
            'value="$1"; runtime_name=LINE_CHANNEL_ACCESS_TOKEN; runtime_env="$2"\n'
            + source[start:end],
            "synthetic-writer",
            token,
            str(env),
        ],
        capture_output=True,
        check=True,
    )
    assert operator.client() == token


def test_secret_failure_never_constructs_client(secret_tree, monkeypatch):
    _, _, env = secret_tree
    env.chmod(0o666)
    monkeypatch.setattr(operator, "LineClient", lambda token: pytest.fail("client reached"))
    with pytest.raises(ValueError, match="^credential_unavailable$"):
        operator.client()


def test_non_root_plan_still_rejected(tmp_path, monkeypatch):
    from scripts.production_config_sync import ConfigSyncError

    path = tmp_path / "plan.json"
    path.write_text("{}")
    actual = path.stat()
    monkeypatch.setattr(
        type(path),
        "lstat",
        lambda self: SimpleNamespace(
            st_mode=actual.st_mode,
            st_uid=12345,
            st_gid=12345,
        ),
    )
    with pytest.raises(ConfigSyncError, match="owner/group"):
        operator.protected(path)


def test_standard_escaped_scalar_decoding():
    assert (
        operator._runtime_token(b"LINE_CHANNEL_ACCESS_TOKEN='synthetic\\'quote'\n")
        == "synthetic'quote"
    )
