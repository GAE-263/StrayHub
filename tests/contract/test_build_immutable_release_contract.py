from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/build-release.yml"
SCRIPT = ROOT / "scripts/build-immutable-release.sh"
DOCKERFILE = ROOT / "infra/gce/images/Dockerfile.release-artifact"


def test_build_workflow_is_main_only_and_serializes_same_sha() -> None:
    document = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    text = WORKFLOW.read_text(encoding="utf-8")

    assert document["on"]["push"]["branches"] == ["main"]
    assert "workflow_dispatch" in document["on"]
    assert "refs/heads/main" in text
    assert "cancel-in-progress: false" in text
    assert (
        "immutable-release-${{ github.event_name == 'workflow_dispatch' && "
        "inputs.git_sha || github.sha }}"
        in text
    )
    assert "google-github-actions/auth@v2" in text
    assert "id-token: write" in text
    assert 'gcloud auth configure-docker "${REGISTRY%%/*}" --quiet' in text
    assert "build-immutable-release.sh" in text
    assert "docker build" not in text


def test_immutable_builder_reuses_registry_identity_before_building() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "gcloud artifacts docker images describe" in text
    assert "if [[ -n \"$artifact_digest\" ]]" in text
    assert "docker cp \"$artifact_container:/release-manifest.json\"" in text
    assert "existing release identity manifest checksum mismatch" in text
    assert "bundle_sha256=%s\\n" in text
    assert "buildx build" in text
    assert "--provenance=true" in text
    assert "--sbom=false" in text
    assert "type=gha,scope=strayhub-$service" in text
    assert "type=gha,mode=max,scope=strayhub-$service" in text
    assert "--label \"org.opencontainers.image.revision=$git_sha\"" in text
    assert "--tag \"$artifact_tag\"" in text
    assert "artifact-identity.env" in text


def test_release_artifact_image_contains_only_nonsecret_identity_files() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")

    for path in (
        "release-manifest.json",
        "checksums.sha256",
        "deployment-bundle.tar",
        "release-identity.json",
    ):
        assert f"COPY {path}" in text
    assert "secret" not in text.lower()
    assert "FROM scratch" in text


def test_bundle_identity_defaults_to_commit_time_instead_of_wall_clock() -> None:
    text = (ROOT / "scripts/build-release-bundle.sh").read_text(encoding="utf-8")

    assert 'git -C "$ROOT_DIR" show -s --format=%ct' in text
    assert "date -u -d \"@$commit_epoch\"" in text
    assert 'created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"' not in text
