"""Transactional outbox creation for volunteer lifecycle notifications."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from services.api.app.api.errors import DomainError
from services.api.app.domain.volunteer_access import request_fingerprint
from services.api.app.persistence.models.volunteer_access import (
    VolunteerNotificationDelivery,
    VolunteerNotificationRetryBatch,
    VolunteerNotificationRetryBatchItem,
)
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)

SAFE_PAYLOAD_FIELDS = frozenset(
    {
        "organization_name",
        "application_status",
        "grant_status",
        "valid_from",
        "expires_at",
        "next_action",
    }
)


def sanitized_notification_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    unexpected = set(payload) - SAFE_PAYLOAD_FIELDS
    if unexpected:
        raise DomainError(
            "notification_payload_not_allowed",
            "通知內容包含不允許的敏感欄位",
            500,
        )
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise DomainError("timezone_required", "通知時間必須包含 UTC 時區", 500)
            sanitized[key] = value.astimezone(timezone.utc).isoformat()
        elif value is None or isinstance(value, (str, int, bool)):
            sanitized[key] = value
        else:
            raise DomainError("notification_payload_invalid", "通知內容格式無效", 500)
    return sanitized


class VolunteerNotificationService:
    def __init__(self, repository: VolunteerAccessRepository) -> None:
        self.repository = repository

    async def enqueue(
        self,
        *,
        user_id: UUID,
        line_binding_id: UUID | None,
        event_type: str,
        resource_type: str,
        resource_id: UUID,
        resource_version: int,
        payload: Mapping[str, Any],
    ) -> VolunteerNotificationDelivery:
        idempotency_key = f"{event_type}:{resource_type}:{resource_id}:v{resource_version}"
        existing = await self.repository.notification_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing
        delivery = VolunteerNotificationDelivery(
            organization_id=self.repository.organization_id,
            user_id=user_id,
            line_binding_id=line_binding_id,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            idempotency_key=idempotency_key,
            payload=sanitized_notification_payload(payload),
            status="pending",
        )
        await self.repository.add(delivery)
        return delivery

    async def retry_failed(
        self,
        *,
        operation_id: UUID,
        notification_ids: list[UUID],
        actor_user_id: UUID,
        platform_support_reason: str | None = None,
        now: datetime | None = None,
    ) -> tuple[VolunteerNotificationRetryBatch, list[VolunteerNotificationRetryBatchItem]]:
        if not notification_ids or len(notification_ids) > 500:
            raise DomainError("invalid_retry_selection", "通知重試必須介於 1 到 500 筆", 422)
        if len(notification_ids) != len(set(notification_ids)):
            raise DomainError("duplicate_retry_target", "通知重試包含重複項目", 422)
        fingerprint = request_fingerprint(
            {"notification_ids": sorted(str(item) for item in notification_ids)}
        )
        existing = await self.repository.retry_batch_by_operation(operation_id)
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise DomainError(
                    "operation_payload_conflict",
                    "相同 operation id 不可使用不同重試內容",
                    409,
                )
            return existing, await self.repository.retry_items(existing.id)
        batch = VolunteerNotificationRetryBatch(
            id=uuid4(),
            organization_id=self.repository.organization_id,
            operation_id=operation_id,
            actor_user_id=actor_user_id,
            platform_support_reason=platform_support_reason,
            request_fingerprint=fingerprint,
            requested_count=len(notification_ids),
            requeued_count=0,
            conflict_count=0,
        )
        items: list[VolunteerNotificationRetryBatchItem] = []
        clock = now or datetime.now(timezone.utc)
        for notification_id in notification_ids:
            delivery = await self.repository.notification(notification_id, for_update=True)
            if delivery is None or delivery.status != "failed":
                result = "conflict"
                error_code = "notification_not_retryable"
                batch.conflict_count += 1
            else:
                delivery.status = "retry_wait"
                delivery.available_at = clock
                delivery.claim_token = None
                delivery.claimed_at = None
                delivery.claimed_by = None
                result = "requeued"
                error_code = None
                batch.requeued_count += 1
            items.append(
                VolunteerNotificationRetryBatchItem(
                    id=uuid4(),
                    organization_id=self.repository.organization_id,
                    batch_id=batch.id,
                    notification_delivery_id=notification_id,
                    result=result,
                    error_code=error_code,
                )
            )
        await self.repository.add(batch)
        await self.repository.add_all(items)
        return batch, items


__all__ = [
    "SAFE_PAYLOAD_FIELDS",
    "VolunteerNotificationService",
    "sanitized_notification_payload",
]
