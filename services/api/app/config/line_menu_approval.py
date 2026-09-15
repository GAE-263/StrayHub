"""Versioned, protected operator attestation; no remote operations or credentials.

Checksums bind reviewed bytes. They are not signatures or proof of human truth.
Only the protected operator workflow may approve, replace or revoke this file.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from services.api.app.config.line_menu_smoke import (
    MAX_AGE,
    SHA256,
    Contract,
    Identity,
    Menu,
    Report,
    config_digest,
    digest,
    expected_report_environment,
    release_identity,
    required_resources,
    utc,
)

if TYPE_CHECKING:
    from services.api.app.config.settings import Settings


class ScopeSnapshot(Contract):
    bot_sha256: str = Field(pattern=SHA256)
    channel_id: str = Field(pattern=r"^[0-9]+$")
    expires_at: str
    user_set_sha256: str = Field(pattern=SHA256)


class Stage(Contract):
    observed_at: str
    principal_reference: str = Field(pattern=r"^account-[0-9]{1,3}$")
    membership: Literal["public", "VOLUNTEER", "STAFF", "SHELTER_ADMIN"]
    scope_sha256: str = Field(pattern=SHA256)
    scope_state: Literal["allowed", "outside", "expired", "cross-tenant"]


class Approval(Contract):
    status: Literal["pending", "approved", "revoked"]
    operator: Literal["yawan0203"]
    approved_at: str
    evidence_sha256: str = Field(pattern=SHA256)
    reference: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")


class ApprovedReport(Contract):
    schema_version: Literal[2]
    account_mode: Literal["single-account-staged"]
    evidence: Report
    scope: ScopeSnapshot
    stages: dict[str, Stage]
    approval: Approval


def evidence_digest(document: dict) -> str:
    return digest(
        json.dumps(
            {k: v for k, v in document.items() if k != "approval"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )


def snapshot(settings: Settings) -> dict:
    hashes = settings.line_role_menu_test_user_sha256.get_secret_value().split(",")
    return {
        "bot_sha256": settings.line_role_menu_bot_sha256,
        "channel_id": settings.line_role_menu_test_channel_id,
        "expires_at": utc(settings.line_role_menu_test_expires_at).isoformat(),
        "user_set_sha256": digest(",".join(sorted(hashes)).encode()),
    }


def validate_approval(document: dict, *, now: datetime | None = None) -> Report:
    """Validate historical evidence; shared validator checks current identity next."""
    approved = ApprovedReport.model_validate(document)
    now = now or datetime.now(timezone.utc)
    report = approved.evidence
    approval = approved.approval
    observed = utc(report.observed_at)
    approved_at = utc(approval.approved_at)
    if (
        approval.status != "approved"
        or approval.evidence_sha256 != evidence_digest(document)
        or not observed <= approved_at <= now
        or approved_at - observed > MAX_AGE
    ):
        raise ValueError("approval invalid or revoked")
    scope = approved.scope
    scope_hash = digest(
        json.dumps(scope.model_dump(), sort_keys=True, separators=(",", ":")).encode()
    )
    if (
        scope_hash != report.scope_sha256
        or scope.channel_id != report.channel_id
        or scope.bot_sha256 != report.bot_sha256
        or utc(scope.expires_at) != utc(report.scope_expires_at)
        or not approved_at < utc(scope.expires_at) <= observed + MAX_AGE
    ):
        raise ValueError("historical scope mismatch")
    human_cases = {name for name, case in report.cases.items() if case.source == "human"}
    if set(approved.stages) != human_cases:
        raise ValueError("stage coverage mismatch")
    principal_refs = set()
    adopter_times = []
    volunteer_times = []
    for name, stage in approved.stages.items():
        at = utc(stage.observed_at)
        if not timedelta(0) <= observed - at <= MAX_AGE:
            raise ValueError("invalid stage time")
        if name.startswith("adopter."):
            principal_refs.add(stage.principal_reference)
            adopter_times.append(at)
            if stage.membership != "public" or stage.scope_state != "allowed":
                raise ValueError("adopter stage identity invalid")
        elif name.startswith("volunteer."):
            principal_refs.add(stage.principal_reference)
            volunteer_times.append(at)
            if stage.membership != "VOLUNTEER" or stage.scope_state != "allowed":
                raise ValueError("volunteer stage identity invalid")
        elif name.startswith("staff."):
            if stage.membership not in {"STAFF", "SHELTER_ADMIN"} or stage.scope_state != "allowed":
                raise ValueError("staff stage identity invalid")
        elif name.startswith("boundary."):
            expected = {
                "boundary.non_test_unchanged": "outside",
                "boundary.expired_denied": "expired",
                "boundary.cross_tenant_denied": "cross-tenant",
            }
            if stage.scope_state != expected.get(name):
                raise ValueError("boundary scope mismatch")
        if stage.scope_state == "allowed" and stage.scope_sha256 != report.scope_sha256:
            raise ValueError("allowed stage scope mismatch")
    if (
        len(principal_refs) != 1
        or not adopter_times
        or not volunteer_times
        or max(adopter_times) >= min(volunteer_times)
    ):
        raise ValueError("single-account sequence invalid")
    return report


class DirectOpening(Contract):
    """Operator risk acceptance, explicitly NOT evidence of successful user testing."""

    schema_version: Literal[3]
    kind: Literal["operator-authorized-direct-opening"]
    environment: Literal["production"]
    candidate: Identity
    channel_id: str = Field(pattern=r"^[0-9]+$")
    bot_sha256: str = Field(pattern=SHA256)
    config_sha256: str = Field(pattern=SHA256)
    resources: dict[str, Menu]
    human_validation: Literal["NOT RUN"]
    accept_unverified_user_flows: bool
    staff_enabled: Literal[False]
    approval: Approval


def validate_direct_opening(
    document: dict, settings: Settings, manifest: dict, resources: dict
) -> None:
    direct = DirectOpening.model_validate(document)
    if (
        direct.approval.status != "approved"
        or direct.approval.evidence_sha256 != evidence_digest(document)
        or utc(direct.approval.approved_at) > datetime.now(timezone.utc)
        or not direct.accept_unverified_user_flows
        or settings.line_staff_menu_enabled
        or settings.line_role_menu_test_enabled
        or direct.environment != expected_report_environment(settings)
        or direct.candidate != release_identity(manifest)
        or direct.channel_id != settings.line_channel_id
        or direct.bot_sha256 != settings.line_role_menu_bot_sha256
        or direct.config_sha256 != config_digest(settings, include_ai=True)
        or set(direct.resources) != {"default", "volunteer", "adoption_hub"}
        or direct.resources != required_resources(settings, resources)
    ):
        raise ValueError("direct opening authorization mismatch")
    for role, menu in direct.resources.items():
        if menu.id != getattr(settings, f"line_rich_menu_{role}_id"):
            raise ValueError("direct opening menu mismatch")
