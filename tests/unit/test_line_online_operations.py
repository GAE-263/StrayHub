"""Synthetic clients only: no cloud, production, LINE or identity writes."""

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from scripts import line_online_gate as gate
from scripts.line_menu_manifest import VerifiedMenuManifest
from scripts.line_menu_rollout import (
    LineClient,
    RolloutError,
    apply_plan,
    plan_switches,
    restoration_plan,
)
from scripts.line_rollout_config import validate_rollout

SHA = "a" * 40
CHECKSUM = "b" * 64
UID = "U" + "1" * 32
OTHER = "U" + "2" * 32


@pytest.fixture
def manifest():
    return VerifiedMenuManifest(
        SHA,
        "@synthetic",
        "c" * 64,
        CHECKSUM,
        {
            role: {
                "id": "richmenu-" + role,
                "definition_sha256": "d" * 64,
                "image_sha256": "e" * 64,
            }
            for role in ("default", "volunteer", "adoption_hub")
        },
    )


class FakeClient:
    def __init__(self):
        self.bindings = {UID: "richmenu-old", OTHER: None, "default": None}
        self.writes = []
        self.fail_after_write = False

    def verify(self, _manifest):
        pass

    def read(self, target):
        return self.bindings[target]

    def switch(self, target, menu):
        self.writes.append((target, menu))
        self.bindings[target] = menu
        if self.fail_after_write:
            raise RolloutError("transport_outcome_unknown")


def prepare(client, manifest):
    return plan_switches(
        client,
        manifest,
        [{"target": UID, "role": "volunteer"}, {"target": OTHER, "role": "default"}],
        source="approved-synthetic-memberships",
    )


def apply(client, manifest, plan, tmp_path, *, authorize=lambda: None):
    return apply_plan(
        client,
        manifest,
        plan,
        receipt=tmp_path / "receipt.json",
        authorize=authorize,
        uid=os.getuid(),
        gid=os.getgid(),
    )


def test_plan_is_read_only_and_records_original_bindings(manifest):
    client = FakeClient()
    plan = prepare(client, manifest)
    assert client.writes == []
    assert [e["before"] for e in plan["entries"]] == ["richmenu-old", None]


def test_success_sanitized_receipt_and_no_repeat(manifest, tmp_path):
    client = FakeClient()
    plan = prepare(client, manifest)
    receipt = apply(client, manifest, plan, tmp_path)
    assert receipt["status"] == "success"
    assert len(client.writes) == 2
    assert UID not in json.dumps(receipt) and OTHER not in json.dumps(receipt)
    with pytest.raises(RolloutError, match="receipt_exists"):
        apply(client, manifest, plan, tmp_path)
    assert len(client.writes) == 2


def test_ambiguous_write_stops_and_exact_restoration_uses_readback(manifest, tmp_path):
    client = FakeClient()
    plan = prepare(client, manifest)
    client.fail_after_write = True
    with pytest.raises(RolloutError, match="unknown"):
        apply(client, manifest, plan, tmp_path)
    receipt = json.loads((tmp_path / "receipt.json").read_bytes())
    assert receipt["status"] == "stopped-readback-required"
    assert len(client.writes) == 1
    restore = restoration_plan(client, manifest, plan, receipt)
    assert restore["entries"] == [
        {"target": UID, "before": "richmenu-volunteer", "after": "richmenu-old"}
    ]
    client.fail_after_write = False
    other = tmp_path / "restore"
    other.mkdir()
    apply(client, manifest, restore, other)
    assert client.bindings == {UID: "richmenu-old", OTHER: None, "default": None}


def test_restore_original_absent_binding_and_never_other_users(manifest, tmp_path):
    client = FakeClient()
    plan = plan_switches(
        client, manifest, [{"target": OTHER, "role": "default"}], source="synthetic"
    )
    receipt = apply(client, manifest, plan, tmp_path)
    restore = restoration_plan(client, manifest, plan, receipt)
    assert restore["entries"] == [{"target": OTHER, "before": "richmenu-default", "after": None}]
    assert client.bindings[UID] == "richmenu-old"


def test_batch_drift_denies_before_first_write(manifest, tmp_path):
    client = FakeClient()
    plan = prepare(client, manifest)
    client.bindings[OTHER] = "richmenu-unrelated"
    with pytest.raises(RolloutError, match="drift"):
        apply(client, manifest, plan, tmp_path)
    assert not client.writes
    assert not (tmp_path / "receipt.json").exists()


def test_gate_change_between_users_stops_without_retry(manifest, tmp_path):
    client = FakeClient()
    plan = prepare(client, manifest)
    calls = []

    def authorize():
        calls.append(1)
        if len(calls) == 3:
            raise ValueError("release_drift")

    with pytest.raises(ValueError, match="release_drift"):
        apply(client, manifest, plan, tmp_path, authorize=authorize)
    assert len(client.writes) == 1
    assert json.loads((tmp_path / "receipt.json").read_text())["entries"][0]["status"] == "verified"


def test_interruption_keeps_write_ahead_intent(manifest, tmp_path, monkeypatch):
    client = FakeClient()
    plan = prepare(client, manifest)

    def interrupt(*_args):
        raise KeyboardInterrupt

    monkeypatch.setattr(client, "switch", interrupt)
    with pytest.raises(KeyboardInterrupt):
        apply(client, manifest, plan, tmp_path)
    receipt = json.loads((tmp_path / "receipt.json").read_text())
    assert receipt["entries"][0]["status"] == "intent-recorded"
    assert receipt["status"] == "stopped-readback-required"


@pytest.mark.parametrize(
    "fault", ["sha", "manifest", "target", "menu", "duplicate", "global-mixed", "extra"]
)
def test_invalid_plans_zero_write(manifest, tmp_path, fault):
    client = FakeClient()
    plan = prepare(client, manifest)
    if fault == "sha":
        plan["git_sha"] = "f" * 40
    elif fault == "manifest":
        plan["manifest_sha256"] = "f" * 64
    elif fault == "target":
        plan["entries"][0]["target"] = "all"
    elif fault == "menu":
        plan["entries"][0]["after"] = "richmenu-staff"
    elif fault == "duplicate":
        plan["entries"].append(plan["entries"][0])
    elif fault == "global-mixed":
        plan["entries"][0]["target"] = "default"
    else:
        plan["ignored"] = True
    with pytest.raises(RolloutError):
        apply(client, manifest, plan, tmp_path)
    assert not client.writes


def test_default_switch_is_separate_and_restore_detects_foreign_change(manifest, tmp_path):
    client = FakeClient()
    plan = plan_switches(
        client, manifest, [{"target": "default", "role": "default"}], source="synthetic"
    )
    receipt = apply(client, manifest, plan, tmp_path)
    client.bindings["default"] = "richmenu-someone-else"
    with pytest.raises(RolloutError, match="drift"):
        restoration_plan(client, manifest, plan, receipt)


def bounded():
    return {
        "schema_version": 1,
        "mode": "bounded",
        "git_sha": SHA,
        "manifest_sha256": CHECKSUM,
        "channel_id": "123456",
        "user_sha256": ["f" * 64],
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }


def test_bounded_config_has_no_global_staff_or_secret_changes(manifest):
    values = validate_rollout(bounded(), manifest, production=False)
    assert values["LINE_ROLE_MENU_TEST_ENABLED"] == "true"
    assert values["LINE_ROLE_MENU_FEATURES_ENABLED"] == "false"
    assert values["LINE_STAFF_MENU_ENABLED"] == "false"
    assert not any("TOKEN" in key or "SECRET" in key for key in values)


def test_explicit_ai_configuration_is_narrow_and_not_a_secret_channel(manifest):
    data = bounded()
    data["ai"] = {"celery_ai_enabled": True, "gemini_model_name": "gemini-synthetic"}
    values = validate_rollout(data, manifest, production=False)
    assert values["CELERY_AI_ENABLED"] == "true"
    assert values["GEMINI_MODEL_NAME"] == "gemini-synthetic"
    data["ai"]["GEMINI_API_KEY"] = "not-allowed"
    with pytest.raises(ValueError):
        validate_rollout(data, manifest, production=False)


@pytest.mark.parametrize(
    "field,value",
    [
        ("expires_at", "2020-01-01T00:00:00Z"),
        ("expires_at", "2099-01-01T00:00:00Z"),
        ("user_sha256", []),
        ("user_sha256", ["*"]),
        ("user_sha256", ["f" * 64] * 2),
        ("mode", "staff"),
        ("git_sha", "b" * 40),
        ("credential", "no"),
    ],
)
def test_invalid_rollout_config_denied(manifest, field, value):
    data = bounded()
    data[field] = value
    with pytest.raises(ValueError):
        validate_rollout(data, manifest, production=False)


@pytest.fixture
def gate_env(monkeypatch):
    for key, value in {
        "GITHUB_ACTOR": "yawan0203",
        "GITHUB_TRIGGERING_ACTOR": "yawan0203",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_REPOSITORY": "GAE-263/StrayHub",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/release",
        "GITHUB_SHA": SHA,
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(
        gate.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 0, stdout=SHA)
    )
    monkeypatch.setattr(
        gate,
        "read_current_release_head",
        lambda a, b, c: a if a == b == c else (_ for _ in ()).throw(ValueError()),
    )


@pytest.mark.parametrize(
    "operation", ["config-sync", "reload-config", "menu-switch", "menu-restore"]
)
def test_manual_plan_gate_success(gate_env, operation):
    gate.authorize(operation, CHECKSUM, SHA, f"LINE ONLINE {operation} {SHA} {CHECKSUM}")


@pytest.mark.parametrize(
    "field,value",
    [
        ("GITHUB_ACTOR", "other"),
        ("GITHUB_TRIGGERING_ACTOR", "other"),
        ("GITHUB_RUN_ATTEMPT", "2"),
        ("GITHUB_EVENT_NAME", "push"),
        ("GITHUB_EVENT_NAME", "pull_request"),
        ("GITHUB_REF", "refs/heads/main"),
        ("GITHUB_REPOSITORY", "other/repo"),
        ("GITHUB_SHA", "c" * 40),
    ],
)
def test_manual_plan_gate_rejects_invalid_context(gate_env, monkeypatch, field, value):
    monkeypatch.setenv(field, value)
    with pytest.raises(ValueError):
        gate.authorize("menu-switch", CHECKSUM, SHA, f"LINE ONLINE menu-switch {SHA} {CHECKSUM}")


def test_workflow_dispatch_only_and_gate_before_wif():
    from scripts.check_sensitive_transport_policy import load_yaml

    workflow = load_yaml(Path(".github/workflows/line-online-operations.yml"))
    assert set(workflow.get("on", workflow.get(True))) == {"workflow_dispatch"}
    job = workflow["jobs"]["operate"]
    assert "github.triggering_actor == 'yawan0203'" in job["if"]
    assert "github.run_attempt == 1" in job["if"]
    steps = job["steps"]
    gate_step = next(
        i for i, step in enumerate(steps) if "scripts.line_online_gate" in step.get("run", "")
    )
    auth_step = next(
        i
        for i, step in enumerate(steps)
        if step.get("uses", "").startswith("google-github-actions/auth")
    )
    assert gate_step < auth_step
    assert not any("upload-artifact" in step.get("uses", "") for step in steps)


def test_bundle_contains_all_operator_stdlib_modules():
    bundle = Path("scripts/build-release-bundle.sh").read_text()
    for name in (
        "production_config_sync",
        "line_menu_manifest",
        "line_rollout_config",
        "line_menu_rollout",
        "line_online_operator",
        "manual_release_gate",
        "release_head_gate",
    ):
        assert f"scripts/{name}.py" in bundle


@pytest.mark.parametrize(
    "method,path,data",
    [
        ("POST", "/v2/bot/richmenu", False),
        ("DELETE", "/v2/bot/richmenu/richmenu-old", False),
        ("POST", "/v2/bot/richmenu/bulk/link", False),
        ("POST", "/v2/bot/message/push", False),
        ("POST", "/v2/bot/user/all/richmenu/richmenu-new", True),
    ],
)
def test_client_forbids_publication_bulk_and_message_endpoints(method, path, data):
    with pytest.raises(RolloutError, match="endpoint_not_allowed"):
        LineClient("synthetic").request(method, path, data=data)


@pytest.mark.parametrize(
    "status,body,expected",
    [(404, b"", None), (200, b'{"richMenuId":"richmenu-old"}', "richmenu-old")],
)
def test_binding_readback_distinguishes_absent_from_error(monkeypatch, status, body, expected):
    client = LineClient("synthetic")
    monkeypatch.setattr(client, "request", lambda *a, **k: (status, body))
    assert client.read(UID) == expected


@pytest.mark.parametrize(
    "status,body",
    [
        (403, b"private-response"),
        (500, b"private-response"),
        (200, b'{"richMenuId":"richmenu-a","richMenuId":"richmenu-b"}'),
        (200, b"not-json"),
    ],
)
def test_failed_binding_readback_never_means_unbound(monkeypatch, status, body):
    client = LineClient("synthetic")
    monkeypatch.setattr(client, "request", lambda *a, **k: (status, body))
    with pytest.raises(RolloutError) as error:
        client.read(UID)
    assert "private-response" not in str(error.value)


@pytest.mark.parametrize(
    "fault",
    ["actor", "triggering_actor", "attempt", "event", "ref", "repository", "sha", "confirmation"],
)
def test_vm_rejects_bad_context_before_github_or_line_credentials(monkeypatch, fault):
    from scripts import line_online_operator as operator

    plan = {"operation": "menu-switch", "git_sha": SHA}
    context = {
        "actor": "yawan0203",
        "triggering_actor": "yawan0203",
        "attempt": "1",
        "repository": "GAE-263/StrayHub",
        "event": "workflow_dispatch",
        "ref": "refs/heads/release",
        "sha": SHA,
        "confirmation": f"LINE ONLINE menu-switch {SHA} {CHECKSUM}",
        "github_token": "synthetic",
    }
    context[fault] = "wrong"
    monkeypatch.setattr(operator, "deployed_sha", lambda: SHA)
    monkeypatch.setattr(
        operator.http.client, "HTTPSConnection", lambda *a, **k: pytest.fail("network reached")
    )
    with pytest.raises(ValueError):
        operator.authorize(context, plan, CHECKSUM)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"ref":"refs/heads/release","object":{"type":"commit","sha":"' + b"b" * 40 + b'"}}',
        b'{"object":{},"object":{}}',
        b"not-json",
    ],
)
def test_vm_rejects_stale_duplicate_malformed_authoritative_head(monkeypatch, raw):
    from scripts import line_online_operator as operator

    plan = {"operation": "menu-switch", "git_sha": SHA}
    context = {
        "actor": "yawan0203",
        "triggering_actor": "yawan0203",
        "attempt": "1",
        "repository": "GAE-263/StrayHub",
        "event": "workflow_dispatch",
        "ref": "refs/heads/release",
        "sha": SHA,
        "confirmation": f"LINE ONLINE menu-switch {SHA} {CHECKSUM}",
        "github_token": "synthetic",
    }

    class Connection:
        status = 200

        def request(self, *a, **k):
            pass

        def getresponse(self):
            return self

        def read(self, _limit):
            return raw

        def close(self):
            pass

    monkeypatch.setattr(operator, "deployed_sha", lambda: SHA)
    monkeypatch.setattr(operator.http.client, "HTTPSConnection", lambda *a, **k: Connection())
    with pytest.raises(RuntimeError):
        operator.authorize(context, plan, CHECKSUM)


def test_keyless_rollout_allows_only_explicit_public_identity(manifest):
    data = bounded()
    data["ai"] = {
        "celery_ai_enabled": True,
        "gemini_model_name": "gemini-synthetic",
        "runtime_identity": {
            "project": "synthetic-project",
            "service_account": "runtime@synthetic-project.iam.gserviceaccount.com",
        },
    }
    values = validate_rollout(data, manifest, production=False)
    assert values["GEMINI_USE_RUNTIME_IDENTITY"] == "true"
    assert values["GEMINI_VERTEX_PROJECT"] == "synthetic-project"
    assert values["LINE_STAFF_MENU_ENABLED"] == "false"
    data["ai"]["runtime_identity"]["private_key"] = "not-allowed"
    with pytest.raises(ValueError, match="runtime_identity_configuration"):
        validate_rollout(data, manifest, production=False)
