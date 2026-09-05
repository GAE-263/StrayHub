#!/usr/bin/env python3
"""Compile StrayHub public-tunnel contracts without changing runtime routing."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES = (
    ROOT / "specs/013-remote-management-public-access/contracts/public-tunnel-profiles.yaml"
)
ALLOWED_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"})
ALLOWED_UPSTREAMS = frozenset({"api", "web"})
MANAGEMENT_ENUMS = {
    "category": frozenset({"management_page", "authentication_api", "management_api"}),
    "caller": frozenset(
        {"browser", "authenticated_browser", "login_page", "authenticated_management_web"}
    ),
    "authentication": frozenset(
        {
            "none",
            "bearer_session_and_public_profile",
            "username_password_json_body",
            "bearer_session_public_profile_role_and_tenant",
        }
    ),
    "query_policy": frozenset({"preserve", "reject_nonempty"}),
    "sensitivity": frozenset(
        {"class_a_entry_surface", "class_a_credential_transport", "internal_management"}
    ),
    "logging_policy": frozenset({"sensitive_path_only"}),
    "rate_limit_expectation": frozenset(
        {
            "gateway_baseline_only",
            "authenticated_baseline_only",
            "account_5_failures_15m_and_ip_20_attempts_15m",
        }
    ),
}
REQUIRED_MANAGEMENT_FIELDS = frozenset(
    {
        "id",
        "category",
        "methods",
        "upstream",
        "owner",
        "purpose",
        "caller",
        "authentication",
        "roles",
        "query_policy",
        "sensitivity",
        "logging_policy",
        "rate_limit_expectation",
        "evidence",
        "tests",
        "demo_required",
    }
)
UUID_PATTERN = (
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
FORBIDDEN_SURFACES = (
    "/v1/platform",
    "/platform",
    "/admin",
    "/settings",
    "/volunteers",
    "/qr-management",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
    "/debug",
    "/internal",
)


class PolicyError(ValueError):
    """A public-tunnel contract is unsafe or incomplete."""


@dataclass(frozen=True, order=True)
class EffectiveRoute:
    id: str
    category: str
    methods: tuple[str, ...]
    upstream: str
    owner: str
    purpose: str
    caller: str
    authentication: str
    roles: tuple[str, ...]
    query_policy: str
    sensitivity: str
    logging_policy: str
    rate_limit_expectation: str
    evidence: tuple[str, ...]
    tests: tuple[str, ...]
    demo_required: bool
    path: str | None = None
    path_pattern: str | None = None


@dataclass(frozen=True)
class CompiledProfile:
    name: str
    frontend_mode: str
    public_management: bool
    routes: tuple[EffectiveRoute, ...]
    exact_assets: tuple[str, ...] = ()
    source_registries: tuple[str, ...] = ()
    asset_source: str | None = None

    @property
    def route_ids(self) -> frozenset[str]:
        return frozenset(route.id for route in self.routes)

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "frontend_mode": self.frontend_mode,
            "public_management": self.public_management,
            "route_count": len(self.routes),
            "route_ids": sorted(self.route_ids),
            "exact_assets": list(self.exact_assets),
            "source_registries": list(self.source_registries),
            "asset_source": self.asset_source,
            "routes": [asdict(route) for route in self.routes],
        }


@dataclass(frozen=True)
class RuntimeOrigin:
    origin: str
    host: str
    hostname: str
    port: int | None


def _require_nonempty(route: Mapping[str, Any], field: str, route_id: str) -> Any:
    value = route.get(field)
    if value is None or value == "" or value == []:
        raise PolicyError(f"route {route_id}: missing {field}")
    return value


def _validate_path(
    route_id: str, path: str | None, pattern: str | None, *, management: bool
) -> None:
    if (path is None) == (pattern is None):
        raise PolicyError(f"route {route_id}: exactly one of path/path_pattern is required")
    candidate = path or pattern or ""
    if any(mark in candidate for mark in ("**", "..", "%", "#", "//", ";")):
        raise PolicyError(f"route {route_id}: unsafe broad or encoded path")
    if path is not None:
        if not path.startswith("/") or "*" in path or "?" in path:
            raise PolicyError(f"route {route_id}: unsafe exact path")
        if (
            management
            and path != "/"
            and (
                any(path.startswith(surface) for surface in FORBIDDEN_SURFACES)
                or "/volunteers" in path
                or "private-profile" in path
            )
        ):
            raise PolicyError(f"route {route_id}: forbidden management surface")
        return
    assert pattern is not None
    if not pattern.startswith("^/") or not pattern.endswith("$"):
        raise PolicyError(f"route {route_id}: pattern must be anchored")
    if ".*" in pattern or ".+" in pattern:
        raise PolicyError(f"route {route_id}: pattern is broader than an approved UUID route")
    if management and ("_next" in pattern or UUID_PATTERN not in pattern):
        raise PolicyError(f"route {route_id}: dynamic pattern must use canonical UUID bounds")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise PolicyError(f"route {route_id}: invalid path pattern") from exc
    literal_prefix = pattern[1:].split("[", 1)[0]
    if management and any(literal_prefix.startswith(surface) for surface in FORBIDDEN_SURFACES):
        raise PolicyError(f"route {route_id}: forbidden management surface")


def _route_from_mapping(route: Mapping[str, Any], *, management: bool) -> EffectiveRoute:
    route_id = str(route.get("id") or "<missing-id>")
    required = (
        REQUIRED_MANAGEMENT_FIELDS if management else REQUIRED_MANAGEMENT_FIELDS - {"demo_required"}
    )
    for field in sorted(required):
        _require_nonempty(route, field, route_id)
    path = route.get("path")
    pattern = route.get("path_pattern")
    _validate_path(route_id, path, pattern, management=management)
    methods = tuple(sorted({str(method).upper() for method in route["methods"]}))
    if not methods or any(method not in ALLOWED_METHODS for method in methods):
        raise PolicyError(f"route {route_id}: invalid method")
    if route["upstream"] not in ALLOWED_UPSTREAMS:
        raise PolicyError(f"route {route_id}: invalid upstream")
    if management:
        for field, allowed in MANAGEMENT_ENUMS.items():
            if route[field] not in allowed:
                raise PolicyError(f"route {route_id}: invalid {field}")
        if route.get("demo_required") is not True:
            raise PolicyError(f"route {route_id}: demo_required must be true")
    roles = tuple(sorted(str(role) for role in route["roles"]))
    if not roles or "PLATFORM_ADMIN" in roles:
        raise PolicyError(f"route {route_id}: invalid public role")
    return EffectiveRoute(
        id=route_id,
        category=str(route["category"]),
        methods=methods,
        upstream=str(route["upstream"]),
        owner=str(route["owner"]),
        purpose=str(route["purpose"]),
        caller=str(route["caller"]),
        authentication=str(route["authentication"]),
        roles=roles,
        query_policy=str(route["query_policy"]),
        sensitivity=str(route["sensitivity"]),
        logging_policy=str(route["logging_policy"]),
        rate_limit_expectation=str(route["rate_limit_expectation"]),
        evidence=tuple(sorted(str(item) for item in route["evidence"])),
        tests=tuple(sorted(str(item) for item in route["tests"])),
        demo_required=bool(route.get("demo_required", False)),
        path=str(path) if path is not None else None,
        path_pattern=str(pattern) if pattern is not None else None,
    )


def validate_management_registry(document: Mapping[str, Any]) -> tuple[EffectiveRoute, ...]:
    if document.get("default_action") != "deny":
        raise PolicyError("management registry must default deny")
    raw_routes = document.get("routes")
    if not isinstance(raw_routes, list):
        raise PolicyError("management registry routes must be a list")
    routes = tuple(_route_from_mapping(route, management=True) for route in raw_routes)
    _validate_unique_ids(routes)
    if len(routes) != 23:
        raise PolicyError(f"management registry: expected 23 routes, found {len(routes)}")
    return tuple(sorted(routes))


def _validate_unique_ids(routes: Sequence[EffectiveRoute]) -> None:
    seen: set[str] = set()
    for route in routes:
        if route.id in seen:
            raise PolicyError(f"duplicate route id: {route.id}")
        seen.add(route.id)


def _line_routes(
    document: Mapping[str, Any], metadata: Mapping[str, Any]
) -> tuple[EffectiveRoute, ...]:
    raw_routes = document.get("routes")
    if not isinstance(raw_routes, list):
        raise PolicyError("LINE registry routes must be a list")
    groups = metadata.get("groups", {})
    group_by_id: dict[str, Mapping[str, Any]] = {}
    for group in groups.values():
        for route_id in group.get("route_ids", []):
            if route_id in group_by_id:
                raise PolicyError(f"LINE compatibility metadata duplicates {route_id}")
            group_by_id[route_id] = group
    routes: list[EffectiveRoute] = []
    for raw in raw_routes:
        route_id = str(raw.get("id") or "<missing-id>")
        group = group_by_id.get(route_id)
        if group is None:
            raise PolicyError(f"LINE compatibility metadata missing {route_id}")
        effective = dict(raw)
        effective.update({key: value for key, value in group.items() if key != "route_ids"})
        effective.update(
            {
                "category": "line_integration",
                "purpose": raw.get("reason"),
                "evidence": sorted(set(raw.get("evidence", [])) | set(raw.get("tests", []))),
                "tests": sorted(set(raw.get("tests", []))),
                "demo_required": False,
            }
        )
        routes.append(_route_from_mapping(effective, management=False))
    ids = {route.id for route in routes}
    if set(group_by_id) != ids:
        raise PolicyError("LINE compatibility metadata contains unknown route ids")
    _validate_unique_ids(routes)
    if len(routes) != 25:
        raise PolicyError(f"LINE registry: expected 25 routes, found {len(routes)}")
    return tuple(sorted(routes))


def _route_sample(route: EffectiveRoute) -> str:
    if route.path is not None:
        return route.path
    assert route.path_pattern is not None
    sample = route.path_pattern[1:-1]
    sample = sample.replace(UUID_PATTERN, "00000000-0000-4000-8000-000000000000")
    sample = sample.replace("(?:/timeline)?", "/timeline")
    sample = sample.replace("[A-Za-z0-9_.()/-]+", "chunks/example.js")
    return sample


def _matches(route: EffectiveRoute, path: str) -> bool:
    if route.path is not None:
        return route.path == path
    return bool(re.fullmatch(route.path_pattern or "", path))


def validate_route_conflicts(routes: Sequence[EffectiveRoute]) -> None:
    for index, left in enumerate(routes):
        for right in routes[index + 1 :]:
            if not set(left.methods).intersection(right.methods):
                continue
            overlaps = _matches(left, _route_sample(right)) or _matches(right, _route_sample(left))
            if not overlaps:
                continue
            security_left = (
                left.upstream,
                left.authentication,
                left.roles,
                left.query_policy,
                left.logging_policy,
                left.rate_limit_expectation,
            )
            security_right = (
                right.upstream,
                right.authentication,
                right.roles,
                right.query_policy,
                right.logging_policy,
                right.rate_limit_expectation,
            )
            if security_left != security_right or left.id != right.id:
                raise PolicyError(f"route conflict: {left.id} overlaps {right.id}")


def _validate_exact_assets(exact_assets: Sequence[str]) -> tuple[str, ...]:
    assets = tuple(sorted(set(exact_assets)))
    for asset in assets:
        if (
            not asset.startswith("/_next/static/")
            or any(mark in asset for mark in ("*", "..", "//", "?", "#", "%"))
            or not asset.endswith((".js", ".css"))
            or asset.endswith(".map")
        ):
            raise PolicyError("production profile contains an unsafe exact asset")
    return assets


def compile_profile_documents(
    profile_name: str,
    profiles_document: Mapping[str, Any],
    line_document: Mapping[str, Any],
    management_document: Mapping[str, Any],
    *,
    exact_assets: Sequence[str] = (),
) -> CompiledProfile:
    profile = profiles_document.get("profiles", {}).get(profile_name)
    if profile is None:
        raise PolicyError(f"unknown profile: {profile_name}")
    registry_specs = profiles_document.get("registries", {})
    requested_registries = profile.get("include_registries", [])
    unknown_registries = set(requested_registries) - set(registry_specs)
    if unknown_registries:
        raise PolicyError(f"unknown registry: {sorted(unknown_registries)[0]}")
    registries: dict[str, tuple[EffectiveRoute, ...]] = {}
    if "line" in requested_registries:
        registries["line"] = _line_routes(
            line_document,
            profiles_document.get("legacy_line_registry_effective_metadata", {}),
        )
    if "management" in requested_registries:
        registries["management"] = validate_management_registry(management_document)
    routes: list[EffectiveRoute] = []
    for registry_name in requested_registries:
        if registry_name not in registries:
            raise PolicyError(f"unknown registry: {registry_name}")
        routes.extend(registries[registry_name])
    _validate_unique_ids(routes)
    route_ids = {route.id for route in routes}
    exclusions = set(profile.get("exclude_route_ids", []))
    unknown = exclusions - route_ids
    if unknown:
        raise PolicyError(f"unknown exclusion: {sorted(unknown)[0]}")
    routes = [route for route in routes if route.id not in exclusions]
    validate_route_conflicts(routes)
    assets = _validate_exact_assets(exact_assets)
    if profile.get("frontend_mode") == "production" and not assets:
        raise PolicyError("production profile requires exact build-manifest assets")
    return CompiledProfile(
        name=profile_name,
        frontend_mode=str(profile["frontend_mode"]),
        public_management=bool(profile["public_management"]),
        routes=tuple(sorted(routes)),
        exact_assets=assets,
        source_registries=tuple(requested_registries),
        asset_source=(
            "next_build_manifest_exact_paths"
            if profile.get("frontend_mode") == "production"
            else "registry_bounded_pattern"
        ),
    )


def _public_page_key(key: str) -> str | None:
    segments = [part for part in key.split("/") if part]
    segments = [part for part in segments if not (part.startswith("(") and part.endswith(")"))]
    if not segments:
        return None
    if segments[-1] == "layout":
        return None
    if segments[-1] == "page":
        segments.pop()
    return "/" + "/".join(segments) if segments else "/"


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError(f"missing or invalid Next manifest: {path.name}") from exc
    if not isinstance(value, dict):
        raise PolicyError(f"invalid Next manifest root: {path.name}")
    return value


def _asset_path(value: Any) -> str | None:
    if not isinstance(value, str):
        raise PolicyError("invalid Next asset entry")
    if not value.startswith("static/") or ".." in value or "//" in value:
        raise PolicyError("unsafe or unknown Next asset")
    if value.endswith(".map"):
        return None
    if not value.endswith((".js", ".css")):
        return None
    return f"/_next/{value}"


def extract_next_public_assets(build_dir: Path, allowed_pages: Iterable[str]) -> tuple[str, ...]:
    build = _load_json(build_dir / "build-manifest.json")
    app = _load_json(build_dir / "app-build-manifest.json")
    pages = app.get("pages")
    if not isinstance(pages, dict):
        raise PolicyError("invalid app build manifest pages")
    requested = set(allowed_pages)
    resolved: set[str] = set()
    selected_entries: list[Sequence[Any]] = []
    selected_internal_keys: list[str] = []
    for key, values in pages.items():
        public = _public_page_key(str(key))
        if public in requested:
            if not isinstance(values, list):
                raise PolicyError(f"invalid assets for page {public}")
            resolved.add(public)
            selected_entries.append(values)
            selected_internal_keys.append(str(key))
    missing = requested - resolved
    if missing:
        raise PolicyError(f"unresolved page in Next manifest: {sorted(missing)[0]}")
    shared: list[Any] = []
    for field in ("polyfillFiles", "rootMainFiles"):
        values = build.get(field, [])
        if not isinstance(values, list):
            raise PolicyError(f"invalid build manifest field: {field}")
        shared.extend(values)
    layout_values: list[Any] = []
    for layout_key, values in pages.items():
        if not str(layout_key).endswith("/layout"):
            continue
        prefix = str(layout_key)[: -len("/layout")]
        if str(layout_key) == "/layout" or any(
            key.startswith(f"{prefix}/") for key in selected_internal_keys
        ):
            if not isinstance(values, list):
                raise PolicyError(f"invalid layout assets: {layout_key}")
            layout_values.extend(values)
    assets = {
        normalized
        for value in [*shared, *layout_values, *(v for values in selected_entries for v in values)]
        if (normalized := _asset_path(value)) is not None
    }
    if not assets:
        raise PolicyError("Next manifest resolved no public assets")
    return tuple(sorted(assets))


def normalize_runtime_origin(
    value: str | None, *, allow_loopback_for_test: bool = False
) -> RuntimeOrigin:
    if not value:
        raise PolicyError("runtime origin is required")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise PolicyError("runtime origin is malformed") from exc
    if parsed.username or parsed.password:
        raise PolicyError("runtime origin must not contain userinfo")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise PolicyError("runtime origin must not contain path, query, or fragment")
    hostname = parsed.hostname
    if not hostname or "*" in hostname or hostname.endswith("."):
        raise PolicyError("runtime origin requires one exact hostname")
    try:
        hostname = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise PolicyError("runtime origin hostname is invalid") from exc
    try:
        address = ipaddress.ip_address(hostname)
        loopback = address.is_loopback
    except ValueError:
        loopback = hostname == "localhost"
    if loopback:
        if not allow_loopback_for_test:
            raise PolicyError("loopback origin requires explicit local validation")
        if parsed.scheme != "http":
            raise PolicyError("local validation origin must use http")
    elif parsed.scheme != "https":
        raise PolicyError("public runtime origin must use https")
    if not loopback and port not in (None, 443):
        raise PolicyError("public runtime origin must use the HTTPS default port")
    effective_port = port if loopback else None
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    authority = f"{display_host}:{effective_port}" if effective_port is not None else display_host
    return RuntimeOrigin(
        origin=f"{parsed.scheme}://{authority}",
        host=authority,
        hostname=hostname,
        port=effective_port,
    )


def runtime_host_matches(origin: RuntimeOrigin, request_host: str) -> bool:
    """Compare an incoming Host authority with a compiler-validated exact authority."""

    if not request_host or any(char in request_host for char in ("/", "?", "#", "@", "*")):
        return False
    try:
        parsed = urlsplit(f"//{request_host}")
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    if not hostname:
        return False
    try:
        hostname = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return False
    expected_port = origin.port or (443 if origin.origin.startswith("https://") else 80)
    actual_port = port or expected_port
    return hostname == origin.hostname and actual_port == expected_port


def compile_profile(
    profile_name: str = "line-only",
    *,
    profiles_path: Path = DEFAULT_PROFILES,
    build_dir: Path | None = None,
    runtime_origin: str | None = None,
    allow_loopback_for_test: bool = False,
) -> tuple[CompiledProfile, RuntimeOrigin | None]:
    profiles = yaml.safe_load(profiles_path.read_text())
    registry_specs = profiles["registries"]
    line_path = (profiles_path.parent / registry_specs["line"]["path"]).resolve()
    line = yaml.safe_load(line_path.read_text())
    management = yaml.safe_load(
        (profiles_path.parent / registry_specs["management"]["path"]).resolve().read_text()
    )
    profile_spec = profiles.get("profiles", {}).get(profile_name)
    if profile_spec is None:
        raise PolicyError(f"unknown profile: {profile_name}")
    assets: tuple[str, ...] = ()
    if profile_spec.get("frontend_mode") == "production":
        if build_dir is None:
            raise PolicyError("production profile requires a Next build directory")
        page_ids = profile_spec["static_assets"]["allowed_page_route_ids"]
        provisional = compile_profile_documents(
            profile_name, profiles, line, management, exact_assets=("/_next/static/placeholder.js",)
        )
        route_by_id = {route.id: route for route in provisional.routes}
        page_paths: list[str] = []
        for route_id in page_ids:
            route = route_by_id.get(route_id)
            if route is None:
                raise PolicyError(f"unknown static page route: {route_id}")
            if route.path is not None:
                page_paths.append(route.path)
            elif route_id == "management_animal_detail_pages":
                page_paths.extend(("/animals/[animalId]", "/animals/[animalId]/timeline"))
            elif route_id == "management_report_detail_page":
                page_paths.append("/reports/[reportId]")
            else:
                raise PolicyError(f"unresolved dynamic page route: {route_id}")
        assets = extract_next_public_assets(build_dir, page_paths)
    compiled = compile_profile_documents(
        profile_name, profiles, line, management, exact_assets=assets
    )
    origin = None
    if compiled.public_management:
        origin = normalize_runtime_origin(
            runtime_origin, allow_loopback_for_test=allow_loopback_for_test
        )
    return compiled, origin


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="line-only")
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--runtime-origin", default=os.environ.get("PUBLIC_TUNNEL_RESERVED_ORIGIN"))
    parser.add_argument("--allow-loopback-for-test", action="store_true")
    args = parser.parse_args(argv)
    try:
        profile, origin = compile_profile(
            args.profile,
            profiles_path=args.profiles,
            build_dir=args.build_dir,
            runtime_origin=args.runtime_origin,
            allow_loopback_for_test=args.allow_loopback_for_test,
        )
    except (OSError, KeyError, TypeError, yaml.YAMLError, PolicyError) as exc:
        parser.error(str(exc))
    output = profile.snapshot()
    output["runtime_origin"] = asdict(origin) if origin is not None else None
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
