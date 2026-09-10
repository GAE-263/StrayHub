"""Synthetic identities only; these tests are not real LINE smoke evidence."""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr
from services.api.app.config.line_menu_smoke import (
    validate_report,
    verified_menu_request,
    webhook_user_allowed,
)
from services.api.app.config.settings import Settings, UnsafeRuntimeConfigurationError
from tests.support.line_menu_smoke import simulated_report
from tests.unit.test_settings_runtime_safety import safe_non_local_settings

UID = "U" + "1" * 32
BOT = "U" + "2" * 32


def scoped_settings(**overrides):
    values = dict(
        _env_file=None,
        app_env="production",
        line_channel_id="1234567890",
        line_role_menu_test_enabled=True,
        line_role_menu_test_channel_id="1234567890",
        line_role_menu_bot_sha256=sha256(BOT.encode()).hexdigest(),
        line_role_menu_test_user_sha256=sha256(UID.encode()).hexdigest(),
        line_role_menu_test_expires_at=(
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).isoformat(),
    )
    values.update(overrides)
    return Settings(**values)


def test_production_scope_allows_only_selected_identity():
    settings = scoped_settings()
    assert settings.line_role_menu_allowed(UID)
    assert not settings.line_role_menu_allowed("U" + "3" * 32)
    assert not settings.line_role_menu_allowed(None)


def test_old_label_alone_does_not_authorize_global_enablement():
    settings = safe_non_local_settings(
        line_role_menu_features_enabled=True,
        web_public_base_url="https://strayhub.enadv.quest",
        line_rich_menu_default_id="richmenu-default-production",
        line_rich_menu_volunteer_id="richmenu-volunteer-production",
        line_rich_menu_staff_id="richmenu-staff-production",
        line_rich_menu_adoption_hub_id="richmenu-hub-production",
        line_staff_liff_id="1234567890-StaffLiff",
        line_role_menu_smoke_evidence=f"verified-20260901-{'a' * 40}",
    )
    with pytest.raises(UnsafeRuntimeConfigurationError, match="report"):
        settings.validate_runtime_safety()


@pytest.mark.parametrize(
    "overrides",
    [
        {"line_role_menu_test_enabled": False},
        {"line_role_menu_test_user_sha256": ""},
        {"line_role_menu_test_user_sha256": "*"},
        {"line_role_menu_test_user_sha256": "a" * 64},
        {"line_role_menu_test_user_sha256": ("a" * 64 + ",") * 10 + "b" * 64},
        {"line_role_menu_test_user_sha256": ",".join(["a" * 64] * 2)},
        {"line_role_menu_test_user_sha256": "A" * 64},
        {"line_role_menu_test_user_sha256": "g" * 64},
        {"line_role_menu_test_user_sha256": "a" * 63},
        {"line_role_menu_test_channel_id": "999"},
        {"line_role_menu_bot_sha256": ""},
        {"line_role_menu_test_expires_at": "2020-01-01T00:00:00+00:00"},
        {"line_role_menu_test_expires_at": "2099-01-01T00:00:00+00:00"},
        {"line_role_menu_test_expires_at": "2099-01-01T00:00:00"},
    ],
)
def test_invalid_scope_is_closed(overrides):
    assert not scoped_settings(**overrides).line_role_menu_allowed(UID)


def test_scope_uses_exact_full_digest_not_prefix_or_substring():
    correct = sha256(UID.encode()).hexdigest()
    assert not scoped_settings(line_role_menu_test_user_sha256=correct[:-1]).line_role_menu_allowed(
        UID
    )
    assert not scoped_settings(
        line_role_menu_test_user_sha256="0" + correct + "0"
    ).line_role_menu_allowed(UID)


@pytest.mark.asyncio
async def test_verified_bot_context_required_and_reset():
    settings = scoped_settings()
    event = {"source": {"type": "user", "userId": UID}}
    assert not webhook_user_allowed(settings, UID)
    for bot, expected in ((BOT, True), ("wrong-bot", False)):
        async with verified_menu_request({"destination": bot, "events": [event]}, settings):
            assert webhook_user_allowed(settings, UID) is expected
            assert not webhook_user_allowed(settings, "U" + "3" * 32)
    assert not webhook_user_allowed(settings, UID)
    event["source"]["type"] = "group"
    async with verified_menu_request({"destination": BOT, "events": [event]}, settings):
        assert not webhook_user_allowed(settings, UID)


@pytest.mark.asyncio
async def test_expiry_and_revocation_are_checked_after_settings_initialization():
    settings = scoped_settings()
    assert settings.line_role_menu_allowed(UID)
    settings.line_role_menu_test_expires_at = "2020-01-01T00:00:00+00:00"
    assert not settings.line_role_menu_allowed(UID)
    settings = scoped_settings()
    settings.line_role_menu_test_enabled = False
    assert not settings.line_role_menu_allowed(UID)


@pytest.mark.asyncio
@pytest.mark.parametrize("eligible,failure", [(True, False), (False, False), (True, True)])
async def test_scoped_hub_handler_uses_real_scope(monkeypatch, eligible, failure):
    from services.api.app.api import line_webhook
    from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter

    settings = scoped_settings(line_rich_menu_adoption_hub_id="richmenu-synthetic-hub")
    monkeypatch.setattr(line_webhook, "get_settings", lambda: settings)
    uid = UID if eligible else "U" + "3" * 32
    event = {
        "type": "postback",
        "replyToken": "synthetic",
        "source": {"type": "user", "userId": uid},
        "postback": {"data": "action=open_adoption_hub"},
    }
    line = MockLineAdapter()
    line.link_rich_menu = AsyncMock(side_effect=RuntimeError("synthetic") if failure else None)
    async with verified_menu_request({"destination": BOT, "events": [event]}, settings):
        assert await line_webhook._handle_menu_action(line, event)
    assert line.link_rich_menu.await_count == int(eligible)
    text = line.replies[0][1][0]["text"]
    if not eligible or failure:
        assert "已切換" not in text
    else:
        assert line.replies[0][1][0]["quickReply"]["items"][0]["action"]["data"] == (
            "action=back_to_default_menu"
        )


@pytest.mark.asyncio
async def test_legacy_worker_router_applies_identical_recipient_scope(monkeypatch):
    from services.worker.app.handlers import volunteer_access_handler as worker

    settings = scoped_settings(
        line_rich_menu_default_id="richmenu-default",
        line_rich_menu_volunteer_id="richmenu-volunteer",
    )
    line = AsyncMock()
    monkeypatch.setattr(worker, "get_worker_settings", lambda: settings)
    monkeypatch.setattr(worker, "LineMessagingApiAdapter", lambda **kwargs: line)
    router = worker._rich_menu_router()
    assert await router.link_for_user(line_user_id=UID, role="VOLUNTEER") == "richmenu-volunteer"
    assert await router.link_for_user(line_user_id="U" + "3" * 32, role="VOLUNTEER") is None
    assert await router.link_for_user(line_user_id="", role=None) is None
    assert line.link_rich_menu.await_count == 1
    line.push.assert_not_called()


def report_settings(tmp_path):
    settings = safe_non_local_settings(
        line_role_menu_features_enabled=True,
        web_public_base_url="https://strayhub.enadv.quest",
        line_rich_menu_default_id="richmenu-default",
        line_rich_menu_volunteer_id="richmenu-volunteer",
        line_rich_menu_adoption_hub_id="richmenu-hub",
        line_rich_menu_staff_id="richmenu-staff",
        line_staff_liff_id="1234567890-Synthetic",
    )
    return settings, simulated_report(settings, tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        "fixture",
        "environment",
        "candidate",
        "image",
        "bot",
        "channel",
        "scope",
        "scope_missing",
        "scope_expiry",
        "scope_config",
        "resources",
        "config",
        "expired",
        "future",
        "missing",
        "fail",
        "not_run",
        "source",
        "staff",
        "checksum",
        "no_report",
        "permissions",
        "no_readback",
    ],
)
def test_global_report_rejects_incomplete_or_mismatched_evidence(tmp_path, mutation):
    settings, report = report_settings(tmp_path)
    if mutation == "fixture":
        report["kind"] = "automated-fixture"
    elif mutation == "environment":
        report["environment"] = "isolated-test"
    elif mutation == "candidate":
        report["candidate"]["git_sha"] = "f" * 40
    elif mutation == "image":
        report["candidate"]["images"]["api"]["digest"] = "sha256:" + "f" * 64
    elif mutation in {"bot", "config"}:
        report[mutation + "_sha256"] = "0" * 64
    elif mutation == "channel":
        report["channel_id"] = "999"
    elif mutation == "scope":
        report["scope_sha256"] = "0" * 64
    elif mutation == "scope_missing":
        del report["scope_sha256"]
    elif mutation == "scope_expiry":
        report["scope_expires_at"] = "2020-01-01T00:00:00Z"
    elif mutation == "resources":
        report["resources"]["default"]["image_sha256"] = "0" * 64
    elif mutation in {"expired", "future"}:
        report["observed_at"] = ("2020" if mutation == "expired" else "2099") + "-01-01T00:00:00Z"
    elif mutation == "missing":
        del report["cases"]["adopter.default_hub"]
    elif mutation in {"fail", "not_run"}:
        report["cases"]["adopter.default_hub"]["result"] = mutation.upper().replace("_", " ")
    elif mutation == "source":
        report["cases"]["adopter.default_hub"]["source"] = "automated"
    elif mutation == "staff":
        report["roles"].remove("staff")
    elif mutation == "no_readback":
        del report["cases"]["resources.readback"]
    path = Path(settings.line_role_menu_report_file)
    path.write_text(json.dumps(report))
    settings.line_role_menu_report_sha256 = sha256(path.read_bytes()).hexdigest()
    if mutation == "checksum":
        settings.line_role_menu_report_sha256 = "0" * 64
    elif mutation == "scope_config":
        settings.line_role_menu_test_user_sha256 = SecretStr("3" * 64)
    elif mutation == "permissions":
        path.chmod(0o666)
    elif mutation == "no_report":
        path.unlink()
    with pytest.raises(ValueError, match="report invalid"):
        validate_report(settings)


def test_complete_simulated_contract_is_not_a_real_smoke_claim(tmp_path):
    settings, _ = report_settings(tmp_path)
    validate_report(settings)
    assert settings.validate_runtime_safety() is settings
    settings.line_staff_liff_id = ""
    with pytest.raises(UnsafeRuntimeConfigurationError, match="LINE_STAFF_LIFF_ID"):
        settings.validate_runtime_safety()


def test_scope_and_old_evidence_in_fresh_process():
    code = """
from tests.unit.test_line_menu_smoke_scope import (
    test_production_scope_allows_only_selected_identity,
    test_old_label_alone_does_not_authorize_global_enablement,
)
test_production_scope_allows_only_selected_identity()
test_old_label_alone_does_not_authorize_global_enablement()
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "APP_ENV": "production"},
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("process", ["api", "worker"])
def test_test_mode_requires_configuration_but_not_evidence(process):
    scope = scoped_settings()
    settings = safe_non_local_settings(
        **{
            key: getattr(scope, key)
            for key in (
                "line_channel_id",
                "line_role_menu_test_enabled",
                "line_role_menu_test_channel_id",
                "line_role_menu_bot_sha256",
                "line_role_menu_test_user_sha256",
                "line_role_menu_test_expires_at",
            )
        },
        web_public_base_url="https://strayhub.enadv.quest",
        line_rich_menu_default_id="richmenu-default",
        line_rich_menu_volunteer_id="richmenu-volunteer",
        line_rich_menu_adoption_hub_id="richmenu-hub",
        line_rich_menu_staff_id="richmenu-staff",
        line_staff_liff_id="1234567890-Synthetic",
    )
    assert settings.validate_runtime_safety(process=process) is settings
    settings.line_role_menu_test_channel_id = "999"
    with pytest.raises(UnsafeRuntimeConfigurationError, match="scope"):
        settings.validate_runtime_safety(process=process)


def test_evidence_cli_template_is_offline_not_run_and_cannot_enable(tmp_path):
    settings, _ = report_settings(tmp_path)
    config = tmp_path / "config.env"
    fields = {key for key in Settings.model_fields if key.startswith("line_rich_menu_")}
    fields |= {
        "line_channel_id",
        "line_role_menu_bot_sha256",
        "web_public_base_url",
        "liff_id",
        "line_staff_liff_id",
        "line_role_menu_report_sha256",
        "line_role_menu_test_channel_id",
        "line_role_menu_test_user_sha256",
        "line_role_menu_test_expires_at",
    }
    config.write_text("\n".join(f"{key.upper()}={getattr(settings, key)}" for key in fields))
    report = tmp_path / "template.json"
    command = [
        sys.executable,
        "-m",
        "scripts.line_menu_smoke_evidence",
        "template",
        "--config-env",
        str(config),
        "--release-manifest",
        settings.line_role_menu_release_file,
        "--resources",
        settings.line_role_menu_resources_file,
        "--report",
        str(report),
    ]
    env = {"PATH": os.environ["PATH"], "APP_ENV": "test"}
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    contents = json.loads(report.read_text())
    assert contents["kind"] == "automated-fixture"
    assert all(case["result"] == "NOT RUN" for case in contents["cases"].values())
    assert UID not in report.read_text()
    assert report.stat().st_mode & 0o777 == 0o600
    # Never overwrite an existing report, even if it is incomplete.
    assert subprocess.run(command, env=env, capture_output=True, timeout=20).returncode == 1
    command[3] = "validate"
    assert subprocess.run(command, env=env, capture_output=True, timeout=20).returncode == 1
