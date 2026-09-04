from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SOURCE_SUFFIXES = {".py", ".sh", ".ts", ".tsx"}
SENSITIVE_KEY = re.compile(
    r"(?:password|secret|credential|authorization|access[_-]?token|refresh[_-]?token|"
    r"id[_-]?token|qr[_-]?token|entry(?:[_-]?reference)?|signed[_-]?url)",
    re.IGNORECASE,
)
QUERY_LITERAL = re.compile(r"[?&](?P<key>[A-Za-z][A-Za-z0-9_.-]*)=")
QUERY_READER = re.compile(
    r"\.(?P<operation>get|has|set)\(\s*[\"'](?P<key>[A-Za-z][A-Za-z0-9_.-]*)[\"']"
)
FORM = re.compile(r"<form\b(?P<attrs>[^>]*)>(?P<body>.*?)</form>", re.IGNORECASE | re.DOTALL)
PASSWORD_FIELD = re.compile(
    r"<(?:input|Input)\b(?=[^>]*(?:type=[\"']password[\"']|name=[\"']password[\"']))[^>]*>",
    re.IGNORECASE | re.DOTALL,
)
HARDCODED_PASSWORD_VALUE = re.compile(
    r"<(?:input|Input)\b(?=[^>]*type=[\"']password[\"'])[^>]*"
    r"value=[\"'][^\"'{][^\"']*[\"'][^>]*>",
    re.IGNORECASE | re.DOTALL,
)
UNSAFE_NGINX_VARIABLES = ("$request ", "$request_uri", "$args", "$http_referer")


@dataclass(frozen=True)
class Candidate:
    path: str
    line: int
    key: str
    rule: str


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    remediation: str

    def render(self) -> str:
        return f"[{self.rule}] {self.path}: {self.remediation}"


def load_yaml(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"Expected a YAML mapping: {path}")
    return document


def registered_keys(registry: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for entry in registry["entries"]:
        for key in [entry["parameter"], *entry.get("aliases", [])]:
            result.setdefault(str(key).casefold(), set()).add(entry["class"])
    return result


def scan_url_candidates(path: str, source: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        for match in QUERY_LITERAL.finditer(line):
            candidates.append(Candidate(path, line_number, match["key"], "query_construction"))
        for match in QUERY_READER.finditer(line):
            candidates.append(Candidate(path, line_number, match["key"], "query_reader"))
    return candidates


def url_violations(
    candidates: Iterable[Candidate],
    registry: dict[str, Any],
    ignores: dict[str, Any],
) -> list[Finding]:
    known = registered_keys(registry)
    exact_ignores = {
        (item["path"], item["rule"], item["parameter"].casefold())
        for item in ignores.get("ignores", [])
    }
    findings: list[Finding] = []
    for candidate in candidates:
        key = candidate.key.casefold()
        if not SENSITIVE_KEY.search(key):
            continue
        if (candidate.path, candidate.rule, key) in exact_ignores:
            continue
        classes = known.get(key, set())
        if not classes:
            findings.append(
                Finding(
                    "ST003",
                    f"{candidate.path}:{candidate.line}",
                    f"remove sensitive URL key {candidate.key!r} or register its "
                    "exact controlled exception",
                )
            )
        elif "A" in classes:
            findings.append(
                Finding(
                    "ST003",
                    f"{candidate.path}:{candidate.line}",
                    f"move Class A key {candidate.key!r} out of the URL into the "
                    "approved body/header",
                )
            )
    return findings


def _unsafe_form_findings(path: str, source: str, *, require_hydration: bool) -> list[Finding]:
    findings: list[Finding] = []
    for match in FORM.finditer(source):
        if not PASSWORD_FIELD.search(match.group("body")):
            continue
        attrs = match.group("attrs")
        if not re.search(r"method=[\"']post[\"']", attrs, re.IGNORECASE) or not re.search(
            r"action=[\"']/login[\"']", attrs, re.IGNORECASE
        ):
            findings.append(
                Finding(
                    "ST001",
                    path,
                    "set the credential form fallback to method=post and action=/login",
                )
            )
    if require_hydration and PASSWORD_FIELD.search(source) and "disabled={!hydrated" not in source:
        findings.append(
            Finding(
                "ST001",
                path,
                "keep login submission disabled until hydration completes",
            )
        )
    return findings


def _hardcoded_password_findings(path: str, source: str) -> list[Finding]:
    if "local-only-password" in source or HARDCODED_PASSWORD_VALUE.search(source):
        return [
            Finding(
                "ST002",
                path,
                "remove production hard-coded password material and use environment/test fixtures",
            )
        ]
    return []


def _nginx_findings(path: str, source: str) -> list[Finding]:
    findings: list[Finding] = []
    for match in re.finditer(r"log_format\s+strayhub_sensitive(?P<body>.*?);", source, re.DOTALL):
        if any(variable in match.group("body") for variable in UNSAFE_NGINX_VARIABLES):
            findings.append(
                Finding(
                    "ST004",
                    path,
                    "use method + $uri sensitive logging without query or Referer variables",
                )
            )
    return findings


def _catchall_findings(path: str, source: str) -> list[Finding]:
    unsafe = bool(
        re.search(r"location\s+\^~\s+/v1/\s*\{[^}]*proxy_pass", source, re.DOTALL)
        or re.search(r"location\s+/\s*\{[^}]*proxy_pass", source, re.DOTALL)
        or 'start_tunnel "Web" "$WEB_PORT"' in source
        or re.search(r"ngrok\s+http\s+[\"']?\$WEB_PORT", source)
    )
    return (
        [
            Finding(
                "ST005",
                path,
                "route the public tunnel only through the default-deny LINE gateway",
            )
        ]
        if unsafe
        else []
    )


def _source_files(root: Path) -> Iterable[Path]:
    for relative in (
        "apps/web/app",
        "apps/web/lib",
        "apps/web/features",
        "services/api/app",
        "services/worker",
        "scripts",
    ):
        source_root = root / relative
        for path in source_root.rglob("*"):
            if path.suffix not in SOURCE_SUFFIXES:
                continue
            if any(part in {"node_modules", ".next", "__pycache__"} for part in path.parts):
                continue
            if path.name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
                continue
            yield path


def check_fixture(root: Path, fixture: Path) -> list[Finding]:
    source = fixture.read_text(encoding="utf-8")
    relative = (
        fixture.relative_to(root).as_posix() if fixture.is_relative_to(root) else fixture.name
    )
    registry = load_yaml(
        root / "specs/012-sensitive-data-transport-hardening/contracts/sensitive-url-registry.yaml"
    )
    findings = _unsafe_form_findings(relative, source, require_hydration=False)
    findings += _hardcoded_password_findings(relative, source)
    findings += url_violations(scan_url_candidates(relative, source), registry, {"ignores": []})
    findings += _nginx_findings(relative, source)
    findings += _catchall_findings(relative, source)
    return findings


def check_repository(root: Path) -> list[Finding]:
    registry = load_yaml(
        root / "specs/012-sensitive-data-transport-hardening/contracts/sensitive-url-registry.yaml"
    )
    ignores = load_yaml(root / "tests/security/fixtures/sensitive_url_scan_ignores.yaml")
    candidates: list[Candidate] = []
    for path in _source_files(root):
        relative = path.relative_to(root).as_posix()
        candidates.extend(scan_url_candidates(relative, path.read_text(encoding="utf-8")))
    findings = url_violations(candidates, registry, ignores)

    login = root / "apps/web/app/login/LoginClient.tsx"
    login_source = login.read_text(encoding="utf-8")
    findings += _unsafe_form_findings(
        login.relative_to(root).as_posix(), login_source, require_hydration=True
    )
    for relative in (
        "apps/web/app/login/LoginClient.tsx",
        "scripts/demo.sh",
        "scripts/demo-line.sh",
        "scripts/seed_demo_accounts.py",
        "scripts/seed_furkids_demo.py",
    ):
        path = root / relative
        findings += _hardcoded_password_findings(relative, path.read_text(encoding="utf-8"))
    for path in (
        root / "infra/local/nginx/line-local.conf.template",
        root / "infra/edge-nginx/strayhub.enadv.quest.conf",
        root / "infra/gce/nginx/strayhub.conf",
    ):
        findings += _nginx_findings(
            path.relative_to(root).as_posix(), path.read_text(encoding="utf-8")
        )
    for path in (
        root / "infra/local/nginx/line-local.conf.template",
        root / "scripts/demo-line.sh",
        root / "scripts/test_line_local.sh",
    ):
        findings += _catchall_findings(
            path.relative_to(root).as_posix(), path.read_text(encoding="utf-8")
        )

    allowlist = load_yaml(
        root / "specs/012-sensitive-data-transport-hardening/contracts/line-tunnel-allowlist.yaml"
    )
    nginx_source = (root / allowlist["gateway"]).read_text(encoding="utf-8")
    for route in allowlist["routes"]:
        if f"allowlist: {route['id']}" not in nginx_source:
            findings.append(
                Finding(
                    "ST006",
                    allowlist["gateway"],
                    f"implement and review the registered tunnel route id {route['id']}",
                )
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Check StrayHub sensitive transport policy")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--fixture", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    findings = (
        check_fixture(root, args.fixture.resolve()) if args.fixture else check_repository(root)
    )
    if findings:
        for finding in findings:
            print(finding.render(), file=sys.stderr)
        print(
            "Remediation: specs/012-sensitive-data-transport-hardening/contracts/"
            "security-boundary.md",
            file=sys.stderr,
        )
        return 1
    print("Sensitive transport policy: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
