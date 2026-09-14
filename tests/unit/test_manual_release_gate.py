from __future__ import annotations

import pytest
from scripts.manual_release_gate import GateError, validate_gate, validate_line_gate

SHA = "a" * 40
BUNDLE = "b" * 64


def context(**overrides: str) -> dict[str, str]:
    values = {
        "actor": "yawan0203",
        "repository": "GAE-263/StrayHub",
        "event_name": "workflow_dispatch",
        "ref": "refs/heads/release",
        "github_sha": SHA,
        "input_sha": SHA,
        "checkout_sha": SHA,
        "release_sha": SHA,
    }
    values.update(overrides)
    return values


def test_publish_and_deploy_confirmations_are_exact() -> None:
    validate_gate(operation="publish", confirmation=f"PUBLISH {SHA}", **context())
    validate_gate(
        operation="deploy",
        confirmation=f"DEPLOY PRODUCTION {SHA} {BUNDLE}",
        bundle_sha256=BUNDLE,
        **context(),
    )


@pytest.mark.parametrize(
    ("operation", "confirmation", "overrides"),
    [
        ("publish", "yes", {}),
        ("publish", f"PUBLISH {SHA[:12]}", {}),
        ("publish", f"publish {SHA}", {}),
        ("publish", f" PUBLISH {SHA}", {}),
        ("publish", f"PUBLISH {SHA} ", {}),
        ("publish", f"PUBLISH {SHA}", {"actor": "someone-else"}),
        ("publish", f"PUBLISH {SHA}", {"ref": "refs/heads/main"}),
        ("publish", f"PUBLISH {SHA}", {"github_sha": "c" * 40}),
        ("publish", f"PUBLISH {SHA}", {"release_sha": "c" * 40}),
        ("deploy", f"DEPLOY PRODUCTION {SHA} {'c' * 64}", {}),
    ],
)
def test_invalid_manual_gate_fails_closed(
    operation: str, confirmation: str, overrides: dict[str, str]
) -> None:
    kwargs = context(**overrides)
    if operation == "deploy":
        kwargs["bundle_sha256"] = BUNDLE
    with pytest.raises(GateError):
        validate_gate(operation=operation, confirmation=confirmation, **kwargs)


@pytest.mark.parametrize("version", ["", "latest", "0", "1;command", "projects/x/versions/1"])
def test_line_gate_rejects_unpinned_secret_versions(version: str) -> None:
    with pytest.raises(GateError):
        validate_line_gate(
            actor="yawan0203",
            repository="GAE-263/StrayHub",
            event_name="workflow_dispatch",
            ref="refs/heads/release",
            github_sha=SHA,
            input_sha=SHA,
            checkout_sha=SHA,
            release_sha=SHA,
            confirmation=f"PUBLISH LINE MENU {SHA}",
            secret_version=version,
        )


def test_line_gate_accepts_only_exact_confirmation() -> None:
    validate_line_gate(
        actor="yawan0203",
        repository="GAE-263/StrayHub",
        event_name="workflow_dispatch",
        ref="refs/heads/release",
        github_sha=SHA,
        input_sha=SHA,
        checkout_sha=SHA,
        release_sha=SHA,
        confirmation=f"PUBLISH LINE MENU {SHA}",
        secret_version="3",
    )
