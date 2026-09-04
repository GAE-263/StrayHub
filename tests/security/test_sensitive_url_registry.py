from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = (
    ROOT
    / "specs"
    / "012-sensitive-data-transport-hardening"
    / "contracts"
    / "sensitive-url-registry.yaml"
)
IGNORES_PATH = ROOT / "tests/security/fixtures/sensitive_url_scan_ignores.yaml"
SOURCE_ROOTS = (
    ROOT / "apps/web/app",
    ROOT / "apps/web/lib",
    ROOT / "apps/web/features",
    ROOT / "services/api/app",
    ROOT / "scripts",
)
SOURCE_SUFFIXES = {".py", ".sh", ".ts", ".tsx"}
REQUIRED_FIELDS = {
    "name",
    "parameter",
    "class",
    "owner",
    "purpose",
    "routes",
    "ttl",
    "reusable",
    "revocable",
    "tenant_scope",
    "resource_scope",
    "logging_policy",
    "referer_policy",
    "analytics_policy",
    "exposure",
    "scrub",
    "mitigation",
    "tests",
    "review_trigger",
}
SENSITIVE_KEY = re.compile(
    r"(?:password|secret|credential|authorization|access[_-]?token|refresh[_-]?token|"
    r"id[_-]?token|qr[_-]?token|entry(?:[_-]?reference)?|signed[_-]?url)",
    re.IGNORECASE,
)
QUERY_LITERAL = re.compile(r"[?&](?P<key>[A-Za-z][A-Za-z0-9_.-]*)=")
QUERY_READER = re.compile(
    r"\.(?P<operation>get|has|set)\(\s*[\"'](?P<key>[A-Za-z][A-Za-z0-9_.-]*)[\"']"
)


@dataclass(frozen=True)
class Candidate:
    path: str
    line: int
    key: str
    rule: str


def _load_yaml(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _registered_keys(registry: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for entry in registry["entries"]:
        for key in [entry["parameter"], *entry.get("aliases", [])]:
            result.setdefault(str(key).casefold(), set()).add(entry["class"])
    return result


def _scan_text(path: str, source: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        for match in QUERY_LITERAL.finditer(line):
            candidates.append(Candidate(path, line_number, match["key"], "query_construction"))
        for match in QUERY_READER.finditer(line):
            candidates.append(Candidate(path, line_number, match["key"], "query_reader"))
    return candidates


def _violations(
    candidates: list[Candidate],
    registry: dict[str, Any],
    ignores: dict[str, Any],
) -> list[str]:
    known = _registered_keys(registry)
    exact_ignores = {
        (item["path"], item["rule"], item["parameter"].casefold()) for item in ignores["ignores"]
    }
    violations: list[str] = []
    for candidate in candidates:
        key = candidate.key.casefold()
        classes = known.get(key, set())
        ignored = (candidate.path, candidate.rule, key) in exact_ignores
        if not SENSITIVE_KEY.search(key):
            continue
        if ignored:
            continue
        if not classes:
            violations.append(
                f"{candidate.path}:{candidate.line} unregistered sensitive URL key "
                f"{candidate.key!r}; "
                "register the exact route/key or remove it"
            )
            continue
        if "A" in classes:
            if candidate.rule != "query_reader":
                violations.append(
                    f"{candidate.path}:{candidate.line} Class A key "
                    f"{candidate.key!r} is forbidden in URLs"
                )
    return violations


def _production_candidates() -> list[Candidate]:
    candidates: list[Candidate] = []
    for source_root in SOURCE_ROOTS:
        for path in source_root.rglob("*"):
            if path.suffix not in SOURCE_SUFFIXES or any(
                part in {"node_modules", ".next", "__pycache__"} for part in path.parts
            ):
                continue
            if path.name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
                continue
            candidates.extend(
                _scan_text(path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8"))
            )
    return candidates


def test_registry_schema_and_class_b_lifecycle_are_complete() -> None:
    registry = _load_yaml(REGISTRY_PATH)
    assert registry["version"] == 1
    assert set(registry["classifications"]) == {"A", "B", "C", "D"}

    entries = registry["entries"]
    assert entries
    assert all(REQUIRED_FIELDS <= entry.keys() for entry in entries)
    assert all(entry["class"] in {"A", "B", "C", "D"} for entry in entries)

    pairs: list[tuple[str, str]] = []
    for entry in entries:
        for route in entry["routes"]:
            for parameter in [entry["parameter"], *entry.get("aliases", [])]:
                pairs.append((route, parameter.casefold()))
        if entry["class"] == "B":
            for field in (
                "owner",
                "ttl",
                "reusable",
                "revocable",
                "logging_policy",
                "tenant_scope",
                "resource_scope",
            ):
                assert entry[field] not in (None, ""), f"{entry['name']} missing {field}"
    assert len(pairs) == len(set(pairs)), "duplicate route/parameter registration"


def test_registry_preserves_known_capability_lifecycles_and_ordinary_queries() -> None:
    entries = {entry["name"]: entry for entry in _load_yaml(REGISTRY_PATH)["entries"]}

    assert entries["volunteer_walk_photo_capability"]["ttl"] == "300_seconds"
    assert entries["public_adoption_photo_capability"]["ttl"] == "300_seconds"
    assert entries["staff_signed_media_url"]["ttl"] == "300_seconds"
    assert entries["volunteer_entry_reference"]["ttl"] == "90_days"
    assert entries["animal_qr_locator"]["ttl"] == "no_fixed_ttl"
    assert entries["animal_qr_locator"]["revocable"] is True
    assert entries["application_status_url_token"]["exposure"] == "not_found"
    assert entries["organization_hint"]["tenant_scope"] == "candidate_only_server_reauthorizes"
    assert entries["search_query"]["logging_policy"] == "retain_on_ordinary_routes"


def test_ignore_rules_are_exact_owned_and_explained() -> None:
    ignores = _load_yaml(IGNORES_PATH)["ignores"]
    assert ignores
    for item in ignores:
        assert set(item) == {"path", "rule", "parameter", "reason", "owner"}
        assert "*" not in item["path"]
        assert (ROOT / item["path"]).is_file()
        assert item["reason"].strip()
        assert item["owner"].strip()


def test_bounded_production_url_scan_has_no_unregistered_sensitive_candidate() -> None:
    violations = _violations(
        _production_candidates(), _load_yaml(REGISTRY_PATH), _load_yaml(IGNORES_PATH)
    )
    assert violations == [], "\n".join(violations)


def test_static_validator_rejects_unknown_sensitive_key_without_echoing_value() -> None:
    candidate = _scan_text("synthetic/new-route.ts", 'const url = "/new?customer_secret=" + value;')
    violations = _violations(candidate, _load_yaml(REGISTRY_PATH), {"ignores": []})

    assert violations
    assert "customer_secret" in violations[0]
    assert "sentinel-value" not in violations[0]


@pytest.mark.parametrize("key", ["page", "query", "date_from", "sort", "status"])
def test_static_validator_accepts_ordinary_query_fixture(key: str) -> None:
    candidates = _scan_text("synthetic/search.ts", f'const url = "/animals?{key}=" + value;')
    assert _violations(candidates, _load_yaml(REGISTRY_PATH), {"ignores": []}) == []
