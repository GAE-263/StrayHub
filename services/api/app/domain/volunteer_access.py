"""Pure volunteer access rules shared by API, worker, and tests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

from services.api.app.api.errors import DomainError

DEFAULT_GRANT_DURATION_HOURS = 168
MAX_SERVICE_DATE_DAYS_AHEAD = 14
ENTRY_REFERENCE_PURPOSE = "volunteer_application_entry"
MAX_REASON_LENGTH = 500


class ApplicationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class GrantStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    RETRY_WAIT = "retry_wait"
    SENT = "sent"
    FAILED = "failed"


def _require_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainError("utc_datetime_required", f"{field} 必須是 UTC-aware 時間", 422)
    return value.astimezone(timezone.utc)


def validate_grant_period(
    valid_from: datetime,
    expires_at: datetime,
    *,
    now: datetime | None = None,
    confirm_immediate_expiry: bool = False,
) -> tuple[datetime, datetime]:
    """Validate and normalize a finite half-open grant period."""

    valid_from = _require_utc(valid_from, "開始時間")
    expires_at = _require_utc(expires_at, "到期時間")
    if expires_at <= valid_from:
        raise DomainError("invalid_grant_period", "到期時間必須晚於開始時間", 422)
    if now is not None:
        now = _require_utc(now, "目前時間")
        if expires_at <= now and not confirm_immediate_expiry:
            raise DomainError(
                "immediate_expiry_confirmation_required",
                "縮短到目前時間以前必須確認立即失效",
                422,
            )
    return valid_from, expires_at


def validate_service_date_selection(
    service_dates: list[date], *, today: date
) -> list[date]:
    """Validate a volunteer's selectable dates in the next 14-day window."""

    if not service_dates:
        raise DomainError("service_date_required", "至少選擇一天服務日期", 422)
    if len(service_dates) != len(set(service_dates)):
        raise DomainError("duplicate_service_date", "服務日期不可重複", 422)
    window_end = today + timedelta(days=MAX_SERVICE_DATE_DAYS_AHEAD - 1)
    if any(service_date < today or service_date > window_end for service_date in service_dates):
        raise DomainError("service_date_out_of_range", "服務日期只能選擇未來兩週內", 422)
    return sorted(service_dates)


def normalize_reason(reason: str | None, *, required: bool = False) -> str | None:
    normalized = reason.strip() if reason is not None else ""
    if required and not normalized:
        raise DomainError("reason_required", "必須提供原因", 422)
    if len(normalized) > MAX_REASON_LENGTH:
        raise DomainError("reason_too_long", "原因不可超過 500 字", 422)
    return normalized or None


def snapshot_policy(*, version: int, duration_hours: int) -> dict[str, int]:
    if version < 1:
        raise DomainError("invalid_policy_version", "政策版本必須大於 0", 422)
    if duration_hours <= 0:
        raise DomainError("invalid_policy_duration", "預設授權期限必須大於 0", 422)
    return {
        "policy_version_used": version,
        "duration_hours_used": duration_hours,
    }


def _json_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return _require_utc(value, "fingerprint datetime").isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def request_fingerprint(payload: Mapping[str, Any]) -> str:
    normalized = json.dumps(
        _json_value(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(normalized.encode()).hexdigest()


def digest_entry_reference(raw_token: str) -> str:
    if len(raw_token.encode()) < 32:
        raise DomainError("entry_reference_too_short", "收容所入口 reference 無效", 403)
    return hashlib.sha256(raw_token.encode()).hexdigest()


def is_effective_volunteer_membership(
    membership: Any,
    grant: Any | None,
    *,
    now: datetime,
    organization_status: str = "active",
    user_status: str = "active",
) -> bool:
    """Apply the shared request-time predicate to a membership-like object."""

    if organization_status != "active" or user_status != "active":
        return False
    if getattr(membership, "status", None) != "active":
        return False
    if getattr(membership, "role", None) != "VOLUNTEER":
        return True
    valid_from = getattr(membership, "valid_from", None)
    expires_at = getattr(membership, "expires_at", None)
    if valid_from is None or expires_at is None or grant is None:
        return False
    now = _require_utc(now, "目前時間")
    valid_from = _require_utc(valid_from, "開始時間")
    expires_at = _require_utc(expires_at, "到期時間")
    return valid_from <= now < expires_at and getattr(grant, "status", None) == "active"


def transition_application(current: str, action: str) -> str:
    target = {
        ("pending", "approve"): "approved",
        ("pending", "reject"): "rejected",
        ("pending", "withdraw"): "withdrawn",
    }.get((current, action))
    if target is None:
        raise DomainError("invalid_application_transition", "申請狀態已改變", 409)
    return target


def transition_grant(current: str, action: str) -> str:
    target = {
        ("active", "expire"): "expired",
        ("active", "revoke"): "revoked",
    }.get((current, action))
    if target is None:
        raise DomainError("invalid_grant_transition", "授權狀態已改變", 409)
    return target


def manual_retry_target(current: str) -> str:
    if current != NotificationStatus.FAILED:
        raise DomainError("notification_retry_conflict", "通知目前不可手動重試", 409)
    return NotificationStatus.RETRY_WAIT
