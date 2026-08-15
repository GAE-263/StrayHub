"""Deterministic builders for volunteer access approval tests.

The builders intentionally return plain dictionaries.  Contract, unit, integration,
and browser fixtures can adapt the same vocabulary without importing persistence
models before the foundational migration exists.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID, uuid5

FIXTURE_NAMESPACE = UUID("a63c6636-0d91-4fe0-9b79-a89e7f74c7e5")
FIXTURE_NOW = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)
ENTRY_PURPOSE = "volunteer_application_entry"


def stable_uuid(label: str) -> UUID:
    """Return a stable UUID for a human-readable fixture label."""

    return uuid5(FIXTURE_NAMESPACE, label)


def organization_fixture(
    code: str = "ORG-A",
    *,
    status: Literal["active", "suspended"] = "active",
) -> dict[str, Any]:
    return {
        "id": stable_uuid(f"organization:{code}"),
        "code": code,
        "name": f"測試收容所 {code}",
        "status": status,
    }


def policy_fixture(
    code: str = "ORG-A",
    *,
    duration_hours: int | None = None,
    applications_enabled: bool = True,
    version: int = 1,
) -> dict[str, Any]:
    if duration_hours is None:
        duration_hours = 72 if code == "ORG-A" else 168
    return {
        "organization_id": stable_uuid(f"organization:{code}"),
        "applications_enabled": applications_enabled,
        "default_grant_duration_hours": duration_hours,
        "version": version,
    }


def entry_reference_fixture(
    code: str = "ORG-A",
    *,
    status: Literal["active", "revoked"] = "active",
) -> dict[str, Any]:
    raw_token = f"local-volunteer-entry-{code.lower()}-" + "a" * 48
    return {
        "id": stable_uuid(f"entry-reference:{code}:{status}"),
        "organization_id": stable_uuid(f"organization:{code}"),
        "purpose": ENTRY_PURPOSE,
        "status": status,
        "raw_token": raw_token,
        "token_digest": hashlib.sha256(raw_token.encode()).hexdigest(),
        "rotation_group_id": stable_uuid(f"entry-rotation:{code}"),
    }


def identity_fixture(
    key: str = "applicant-pending-a",
    *,
    persisted: bool = True,
    user_status: Literal["active", "disabled"] = "active",
) -> dict[str, Any]:
    return {
        "key": key,
        "line_user_id": f"Ulocal-{key}",
        "id_token": f"local-id-token:{key}",
        "user_id": stable_uuid(f"user:{key}") if persisted else None,
        "binding_id": stable_uuid(f"line-binding:{key}") if persisted else None,
        "user_status": user_status,
    }


def application_fixture(
    status: Literal["pending", "approved", "rejected", "withdrawn"] = "pending",
    *,
    code: str = "ORG-A",
    user_key: str = "applicant-pending-a",
    sequence: int = 1,
    version: int = 1,
) -> dict[str, Any]:
    submitted_at = FIXTURE_NOW - timedelta(hours=sequence)
    application: dict[str, Any] = {
        "id": stable_uuid(f"application:{code}:{user_key}:{sequence}"),
        "organization_id": stable_uuid(f"organization:{code}"),
        "user_id": stable_uuid(f"user:{user_key}"),
        "status": status,
        "source_channel": "liff",
        "client_request_id": stable_uuid(f"client-request:{code}:{user_key}:{sequence}"),
        "submitted_at": submitted_at,
        "version": version,
    }
    if status in {"approved", "rejected"}:
        application["decided_at"] = submitted_at + timedelta(minutes=30)
        application["decided_by_user_id"] = stable_uuid(f"admin:{code}")
    if status == "rejected":
        application["decision_reason"] = "本次名額已滿，請聯絡收容所管理員"
    if status == "withdrawn":
        application["withdrawn_at"] = submitted_at + timedelta(minutes=15)
    return application


def grant_fixture(
    status: Literal["active", "expired", "revoked"] = "active",
    *,
    code: str = "ORG-A",
    user_key: str = "volunteer-a",
    valid_from: datetime | None = None,
    duration_hours: int | None = None,
    sequence: int = 1,
) -> dict[str, Any]:
    if valid_from is None:
        valid_from = FIXTURE_NOW - timedelta(hours=1)
    if duration_hours is None:
        duration_hours = 72 if code == "ORG-A" else 168
    expires_at = valid_from + timedelta(hours=duration_hours)
    if status == "expired":
        valid_from = FIXTURE_NOW - timedelta(hours=duration_hours + 1)
        expires_at = FIXTURE_NOW - timedelta(hours=1)
    grant: dict[str, Any] = {
        "id": stable_uuid(f"grant:{code}:{user_key}:{sequence}"),
        "organization_id": stable_uuid(f"organization:{code}"),
        "user_id": stable_uuid(f"user:{user_key}"),
        "membership_id": stable_uuid(f"membership:{code}:{user_key}"),
        "application_id": stable_uuid(f"application:{code}:{user_key}:{sequence}"),
        "status": status,
        "valid_from": valid_from,
        "expires_at": expires_at,
        "approved_at": valid_from,
        "policy_version_used": 1,
        "duration_hours_used": duration_hours,
        "source_type": "manager_approval",
        "version": 1,
    }
    if status == "revoked":
        grant.update(
            revoked_at=FIXTURE_NOW,
            revoked_by_user_id=stable_uuid(f"admin:{code}"),
            revocation_reason="志工本人要求停止本次授權",
        )
    return grant


def invalidation_context_fixture(
    *,
    code: str = "ORG-A",
    user_key: str = "disabled-volunteer-a",
    user_status: Literal["active", "disabled"] = "disabled",
    organization_status: Literal["active", "suspended"] = "active",
) -> dict[str, Any]:
    return {
        "organization": organization_fixture(code, status=organization_status),
        "identity": identity_fixture(user_key, user_status=user_status),
        "session_id": stable_uuid(f"session:{code}:{user_key}"),
        "active_organization_id": stable_uuid(f"organization:{code}"),
        "webhook_session_id": stable_uuid(f"webhook-session:{code}:{user_key}"),
        "cleaned_up": False,
    }


def notification_fixture(
    event_type: str = "approved",
    *,
    code: str = "ORG-A",
    user_key: str = "volunteer-a",
    status: Literal["pending", "sending", "retry_wait", "sent", "failed"] = "failed",
) -> dict[str, Any]:
    return {
        "id": stable_uuid(f"notification:{code}:{user_key}:{event_type}"),
        "organization_id": stable_uuid(f"organization:{code}"),
        "user_id": stable_uuid(f"user:{user_key}"),
        "event_type": event_type,
        "resource_type": (
            "grant" if event_type not in {"application_submitted", "rejected"} else "application"
        ),
        "resource_id": stable_uuid(f"notification-resource:{code}:{user_key}:{event_type}"),
        "idempotency_key": f"{event_type}:{code}:{user_key}:1",
        "status": status,
        "attempt_count": 3 if status == "failed" else 0,
        "last_failed_at": FIXTURE_NOW if status in {"retry_wait", "failed"} else None,
        "last_error_code": "line_delivery_failed" if status == "failed" else None,
    }


def batch_application_fixtures(
    count: int,
    *,
    code: str = "ORG-A",
    start: int = 1,
) -> list[dict[str, Any]]:
    return [
        application_fixture(
            code=code,
            user_key=f"batch-{index:04d}-{code.lower()}",
            sequence=index,
        )
        for index in range(start, start + count)
    ]


def volunteer_access_fixture_matrix() -> dict[str, Any]:
    """Return the shared ORG-A/ORG-B vocabulary used across all story tests."""

    return {
        "organizations": [organization_fixture("ORG-A"), organization_fixture("ORG-B")],
        "policies": [policy_fixture("ORG-A"), policy_fixture("ORG-B")],
        "disabled_application_policy": policy_fixture(
            "ORG-C", applications_enabled=False, duration_hours=168
        ),
        "entry_references": [entry_reference_fixture("ORG-A"), entry_reference_fixture("ORG-B")],
        "unknown_identity": identity_fixture("applicant-new", persisted=False),
        "applications": {
            state: application_fixture(state, user_key=f"applicant-{state}")
            for state in ("pending", "approved", "rejected", "withdrawn")
        },
        "grants": {
            "future": grant_fixture(
                valid_from=FIXTURE_NOW + timedelta(hours=1), user_key="future-a"
            ),
            "active": grant_fixture(user_key="active-a"),
            "expired": grant_fixture("expired", user_key="expired-a"),
            "revoked": grant_fixture("revoked", user_key="revoked-a"),
        },
        "invalid_contexts": [
            invalidation_context_fixture(),
            invalidation_context_fixture(
                code="ORG-B",
                user_key="suspended-org-volunteer-b",
                user_status="active",
                organization_status="suspended",
            ),
        ],
        "failed_notifications": [
            notification_fixture(event_type)
            for event_type in (
                "application_submitted",
                "application_withdrawn",
                "approved",
                "rejected",
                "grant_changed",
                "expired",
                "revoked",
            )
        ],
        "manual_batch": batch_application_fixtures(100),
        "all_filtered_batch": batch_application_fixtures(1200, start=1001),
        "cross_tenant_control": batch_application_fixtures(10, code="ORG-B"),
    }
