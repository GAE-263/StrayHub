"""Offline, fail-closed menu smoke contracts. No LINE client or DB dependencies."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

if TYPE_CHECKING:
    from services.api.app.config.settings import Settings

SHA256 = r"^[0-9a-f]{64}$"
MAX_AGE = timedelta(days=7)
CASES = {
    "adopter": ("default_hub", "matching_entry", "diary_entry", "return_default"),
    "volunteer": ("two_panel", "walk_authorized", "return_default", "role_resync"),
    "staff": ("staff_liff", "staff_tenant_authorized"),
    "boundary": ("non_test_unchanged", "expired_denied", "cross_tenant_denied"),
}
RESOURCE_ROLES = frozenset({"default", "volunteer", "adoption_hub", "staff"})
_verified_webhook_users: ContextVar[frozenset[str]] = ContextVar(
    "line_menu_verified_users", default=frozenset()
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class EvidenceRequirements:
    roles: tuple[str, ...]
    resource_roles: tuple[str, ...]
    human_cases: frozenset[str]


def evidence_requirements(settings: Settings) -> EvidenceRequirements:
    roles = ["adopter", "volunteer"]
    resource_roles = ["default", "volunteer", "adoption_hub"]
    if settings.line_staff_menu_enabled:
        roles.append("staff")
        resource_roles.append("staff")
    human_roles = set(roles) | {"boundary"}
    return EvidenceRequirements(
        roles=tuple(roles),
        resource_roles=tuple(resource_roles),
        human_cases=frozenset(f"{role}.{case}" for role in human_roles for case in CASES[role]),
    )


def required_roles(settings: Settings) -> tuple[str, ...]:
    return evidence_requirements(settings).roles


def required_resource_roles(settings: Settings) -> tuple[str, ...]:
    return evidence_requirements(settings).resource_roles


def required_human_cases(settings: Settings) -> frozenset[str]:
    return evidence_requirements(settings).human_cases


def utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc)


def scope_valid(settings: Settings, *, now: datetime | None = None) -> bool:
    return bool(settings.line_role_menu_test_enabled and _scope_contract_valid(settings, now=now))


def _scope_contract_valid(settings: Settings, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    try:
        expires, hashes = _scope_parts(settings)
        return bool(
            re.fullmatch(r"[0-9]+", settings.line_channel_id)
            and settings.line_role_menu_test_channel_id == settings.line_channel_id
            and re.fullmatch(SHA256, settings.line_role_menu_bot_sha256)
            and 1 <= len(hashes) <= 10
            and len(set(hashes)) == len(hashes)
            and all(re.fullmatch(SHA256, item) for item in hashes)
            and now < expires <= now + MAX_AGE
        )
    except (ValueError, TypeError):
        return False


def _scope_parts(settings: Settings) -> tuple[datetime, list[str]]:
    return (
        utc(settings.line_role_menu_test_expires_at),
        settings.line_role_menu_test_user_sha256.get_secret_value().split(","),
    )


def scope_digest(settings: Settings) -> str:
    """Fingerprint the reviewed account scope without disclosing account hashes."""
    expires, hashes = _scope_parts(settings)
    payload = {
        "bot_sha256": settings.line_role_menu_bot_sha256,
        "channel_id": settings.line_role_menu_test_channel_id,
        "expires_at": expires.isoformat(),
        "user_set_sha256": digest(",".join(sorted(hashes)).encode()),
    }
    return digest(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def scoped_user(settings: Settings, uid: str | None) -> bool:
    if not uid or not re.fullmatch(r"U[0-9a-f]{32}", uid) or not scope_valid(settings):
        return False
    candidate = digest(uid.encode())
    return any(
        hmac.compare_digest(candidate, configured)
        for configured in settings.line_role_menu_test_user_sha256.get_secret_value().split(",")
    )


@asynccontextmanager
async def verified_menu_request(payload: dict, settings: Settings):
    """Call ONLY after signature verification; never accept query/self-reported auth.

    Context is reset even on errors and contains only hashes. Group/room sources
    deliberately cannot opt into the test mode.
    """
    users = (
        frozenset(
            digest(source["userId"].encode())
            for event in payload.get("events", [])
            if isinstance(source := event.get("source"), dict)
            and source.get("type") == "user"
            and isinstance(source.get("userId"), str)
        )
        if (
            isinstance(payload.get("destination"), str)
            and digest(payload["destination"].encode()) == settings.line_role_menu_bot_sha256
        )
        else frozenset()
    )
    token = _verified_webhook_users.set(users)
    try:
        yield
    finally:
        _verified_webhook_users.reset(token)


def webhook_user_allowed(settings: Settings, uid: str | None) -> bool:
    if settings.line_role_menu_features_active():
        return True
    return bool(
        uid and digest(uid.encode()) in _verified_webhook_users.get() and scoped_user(settings, uid)
    )


def webhook_user_verified(uid: str | None) -> bool:
    """Confirm the user belongs to the current signature-verified LINE request."""
    return bool(uid and digest(uid.encode()) in _verified_webhook_users.get())


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Menu(Contract):
    id: str = Field(pattern=r"^richmenu-[a-zA-Z0-9-]+$")
    definition_sha256: str = Field(pattern=SHA256)
    image_sha256: str = Field(pattern=SHA256)


def required_resources(settings: Settings, resources: dict) -> dict[str, Menu]:
    requirements = evidence_requirements(settings)
    if not set(requirements.resource_roles).issubset(resources) or not set(resources).issubset(
        RESOURCE_ROLES
    ):
        raise ValueError("report resource scope incomplete")
    return {role: Menu.model_validate(resources[role]) for role in requirements.resource_roles}


class Identity(Contract):
    git_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    images: dict[str, dict[str, str]]
    compose_sha256: str = Field(pattern=SHA256)
    release_bundle_sha256: str = Field(pattern=SHA256)


class Case(Contract):
    result: Literal["PASS", "FAIL", "NOT RUN"]
    source: Literal["human", "automated"]
    # Opaque protected audit reference, never a UID, URL or free-text transcript.
    reference: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")


class Report(Contract):
    schema_version: Literal[1]
    kind: Literal["real-line", "automated-fixture"]
    environment: Literal["production", "production-like", "isolated-test"]
    observed_at: str
    candidate: Identity
    channel_id: str = Field(pattern=r"^[0-9]+$")
    bot_sha256: str = Field(pattern=SHA256)
    scope_sha256: str = Field(pattern=SHA256)
    scope_expires_at: str
    config_sha256: str = Field(pattern=SHA256)
    resources: dict[str, Menu]
    roles: list[Literal["adopter", "volunteer", "staff"]]
    identity_protection: Literal["protected-config-hashes-no-uid"]
    cases: dict[str, Case]


def expected_report_environment(settings: Settings) -> Literal["production", "production-like"]:
    environment = settings.app_env.strip().lower()
    if environment == "production":
        return "production"
    if environment == "acceptance":
        return "production-like"
    raise ValueError("unsupported LINE role-menu evidence environment")


def config_digest(settings: Settings, *, include_ai: bool = False) -> str:
    # Test enablement/list/expiry and the global role-menu flag are intentionally excluded:
    # moving from scoped to global is the sole permitted transition without retest. The
    # independent Staff flag remains included because it changes evidence requirements.
    names = [
        "line_channel_id",
        "line_role_menu_bot_sha256",
        "web_public_base_url",
        "liff_id",
        "line_staff_menu_enabled",
        "line_rich_menu_default_id",
        "line_rich_menu_volunteer_id",
        "line_rich_menu_adoption_hub_id",
        "line_rich_menu_adopter_id",
        "line_rich_menu_region_select_id",
        "line_rich_menu_path_select_id",
    ]
    if include_ai:
        names.extend(
            (
                "celery_ai_enabled",
                "gemini_model_name",
                "gemini_vertex_location",
                "ai_provider",
                "ai_model_name",
                "ai_endpoint",
            )
        )
    if settings.line_staff_menu_enabled:
        names.extend(("line_staff_liff_id", "line_rich_menu_staff_id"))
    return digest(
        json.dumps(
            {name: getattr(settings, name) for name in names}, sort_keys=True, separators=(",", ":")
        ).encode()
    )


def protected_bytes(filename: str) -> bytes:
    """Root/operator-owned regular files, not writable by other principals.

    Provenance is an operator responsibility, not something a checksum proves.
    """
    if not filename:
        raise ValueError("missing protected report or identity file")
    path = Path(filename)
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o022
            or info.st_uid not in {0, os.geteuid()}
            or info.st_size > 1_000_000
        ):
            raise ValueError("unsafe protected report file")
        raw = stream.read(1_000_001)
    return raw


def protected_json(filename: str) -> tuple[dict, str]:
    raw = protected_bytes(filename)

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    data = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
    if not isinstance(data, dict):
        raise ValueError("invalid report document")
    return data, digest(raw)


def release_identity(manifest: dict) -> Identity:
    identity = Identity.model_validate({key: manifest[key] for key in Identity.model_fields})
    if set(identity.images) != {"api", "worker", "web"}:
        raise ValueError("missing release image identity")
    for image in identity.images.values():
        if (
            set(image) != {"repository", "digest"}
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", image["digest"])
            or not re.fullmatch(r"[a-z0-9][a-z0-9._/-]+", image["repository"])
        ):
            raise ValueError("invalid release image identity")
    return identity


def validate_report(settings: Settings) -> None:
    try:
        data, checksum = protected_json(settings.line_role_menu_report_file)
        if checksum != settings.line_role_menu_report_sha256:
            raise ValueError("report checksum mismatch")
        if data.get("schema_version") == 3:
            from services.api.app.config.line_menu_approval import validate_direct_opening

            manifest, _ = protected_json(settings.line_role_menu_release_file)
            resources, _ = protected_json(settings.line_role_menu_resources_file)
            validate_direct_opening(data, settings, manifest, resources)
            return
        durable = data.get("schema_version") == 2
        if durable:
            from services.api.app.config.line_menu_approval import validate_approval

            report = validate_approval(data)
        else:
            report = Report.model_validate(data)
        manifest, _ = protected_json(settings.line_role_menu_release_file)
        resources, _ = protected_json(settings.line_role_menu_resources_file)
        requirements = evidence_requirements(settings)
        expected = required_resources(settings, resources)
        expected_environment = expected_report_environment(settings)
        if report.kind != "real-line" or report.environment != expected_environment:
            raise ValueError("report must contain real LINE evidence")
        age = datetime.now(timezone.utc) - utc(report.observed_at)
        if not durable and not timedelta(0) <= age <= MAX_AGE:
            raise ValueError("report expired or future dated")
        if report.candidate != release_identity(manifest):
            raise ValueError("report candidate mismatch; equivalent trees are not accepted")
        if (
            report.channel_id != settings.line_channel_id
            or report.bot_sha256 != settings.line_role_menu_bot_sha256
        ):
            raise ValueError("report Bot/Channel mismatch")
        scope_expiry = utc(report.scope_expires_at)
        if not durable and (
            not _scope_contract_valid(settings)
            or report.scope_sha256 != scope_digest(settings)
            or report.scope_expires_at != utc(settings.line_role_menu_test_expires_at).isoformat()
            or not datetime.now(timezone.utc) < scope_expiry <= utc(report.observed_at) + MAX_AGE
        ):
            raise ValueError("report account scope mismatch or expired")
        if (
            report.config_sha256 != config_digest(settings, include_ai=durable)
            or report.resources != expected
        ):
            raise ValueError("report config/resources mismatch")
        for role, menu in expected.items():
            if menu.id != getattr(settings, f"line_rich_menu_{role}_id"):
                raise ValueError("report menu ID mismatch")
        if set(report.roles) != set(requirements.roles) or len(report.roles) != len(
            requirements.roles
        ):
            raise ValueError("report role scope incomplete")
        if set(report.cases) != requirements.human_cases | {"resources.readback"}:
            raise ValueError("report case scope mismatch")
        for case in requirements.human_cases:
            result = report.cases.get(case)
            if result is None or result.result != "PASS" or result.source != "human":
                raise ValueError("report required human case incomplete")
        auto = report.cases.get("resources.readback")
        if auto is None or auto.result != "PASS" or auto.source != "automated":
            raise ValueError("report resource readback incomplete")
        if any(case.result != "PASS" for case in report.cases.values()):
            raise ValueError("report contains incomplete or failed case")
    except (OSError, ValueError, KeyError, TypeError, ValidationError):
        # Never include validation input, filenames, identity or JSON in errors.
        raise ValueError("LINE_ROLE_MENU_SMOKE_EVIDENCE report invalid or incomplete") from None
