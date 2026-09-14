from __future__ import annotations

import pytest
from scripts.manual_release_gate import (
    GateError,
    create_publication_receipt,
    validate_gate,
    validate_line_gate,
    validate_publication_receipt,
)

SHA = "a" * 40
BUNDLE = "b" * 64


def context(**overrides: str) -> dict[str, str]:
    values = {
        "actor": "yawan0203",
        "triggering_actor": "yawan0203",
        "run_attempt": "1",
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


@pytest.mark.parametrize("operation", ["publish", "deploy", "line"])
@pytest.mark.parametrize(
    "overrides",
    [
        {"triggering_actor": "someone-else", "run_attempt": "2"},
        {"triggering_actor": ""},
        {"run_attempt": ""},
        {"run_attempt": "not-a-number"},
        {"run_attempt": "2"},
        {"actor": "someone-else"},
    ],
)
def test_manual_writes_reject_rerun_or_actor_mismatch(
    operation: str, overrides: dict[str, str]
) -> None:
    kwargs = context(**overrides)
    with pytest.raises(GateError):
        if operation == "line":
            validate_line_gate(
                confirmation=f"PUBLISH LINE MENU {SHA}", secret_version="3", **kwargs
            )
        else:
            validate_gate(
                operation=operation,
                confirmation=(
                    f"PUBLISH {SHA}"
                    if operation == "publish"
                    else f"DEPLOY PRODUCTION {SHA} {BUNDLE}"
                ),
                bundle_sha256=BUNDLE if operation == "deploy" else None,
                **kwargs,
            )


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
            triggering_actor="yawan0203",
            run_attempt="1",
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
        triggering_actor="yawan0203",
        run_attempt="1",
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


def test_publication_receipt_binds_manifest_images_and_bundle(tmp_path) -> None:
    manifest = tmp_path / "release-manifest.json"
    receipt = tmp_path / "publication-receipt.json"
    manifest.write_text(
        __import__("json").dumps(
            {
                "git_sha": SHA,
                "release_id": f"20260914T000000Z-{SHA[:12]}",
                "release_bundle_sha256": BUNDLE,
                "images": {
                    service: {"repository": f"example/{service}", "digest": f"sha256:{index * 64}"}
                    for service, index in (("api", "1"), ("worker", "2"), ("web", "3"))
                },
            }
        ),
        encoding="utf-8",
    )
    create_publication_receipt(manifest, receipt, "123")
    validate_publication_receipt(receipt, manifest, git_sha=SHA, bundle_sha256=BUNDLE, run_id="123")
    document = __import__("json").loads(receipt.read_text(encoding="utf-8"))
    document["release_bundle_sha256"] = "c" * 64
    receipt.write_text(__import__("json").dumps(document), encoding="utf-8")
    with pytest.raises(GateError, match="does not match"):
        validate_publication_receipt(
            receipt, manifest, git_sha=SHA, bundle_sha256=BUNDLE, run_id="123"
        )
