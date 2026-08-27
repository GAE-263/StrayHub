"""Immutable target snapshot and resumable volunteer decision batch rules."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any, TypeVar
from uuid import UUID, uuid4

from services.api.app.api.errors import DomainError
from services.api.app.domain.volunteer_access import (
    effective_grant_duration_hours,
    request_fingerprint,
    validate_grant_period,
)
from services.api.app.persistence.models.volunteer_access import (
    VolunteerDecisionBatch,
    VolunteerDecisionBatchItem,
)
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)

MAX_BATCH_CHUNK_SIZE = 500
T = TypeVar("T")


def chunk_targets(targets: Sequence[T], size: int = MAX_BATCH_CHUNK_SIZE) -> Iterator[list[T]]:
    if size < 1 or size > MAX_BATCH_CHUNK_SIZE:
        raise DomainError("invalid_batch_chunk_size", "批次分段必須介於 1 到 500", 422)
    for start in range(0, len(targets), size):
        yield list(targets[start : start + size])


def validate_explicit_items(items: Iterable[tuple[UUID, int]]) -> list[tuple[UUID, int]]:
    normalized = list(items)
    if not normalized or len(normalized) > MAX_BATCH_CHUNK_SIZE:
        raise DomainError("invalid_explicit_selection", "明確選取必須介於 1 到 500 筆", 422)
    identifiers = [application_id for application_id, _ in normalized]
    if len(identifiers) != len(set(identifiers)):
        raise DomainError("duplicate_batch_target", "批次選取包含重複申請", 422)
    if any(version < 1 for _, version in normalized):
        raise DomainError("invalid_application_version", "申請版本無效", 422)
    return normalized


def merge_decision_period(
    *,
    now: datetime,
    policy_duration_hours: int,
    common_valid_from: datetime | None,
    common_expires_at: datetime | None,
    override_valid_from: datetime | None,
    override_expires_at: datetime | None,
) -> tuple[datetime, datetime]:
    valid_from = override_valid_from or common_valid_from or now
    expires_at = (
        override_expires_at
        or common_expires_at
        or valid_from + timedelta(hours=policy_duration_hours)
    )
    return validate_grant_period(valid_from, expires_at)


def terminal_batch_status(requested: int, *, succeeded: int, conflict: int, failed: int) -> str:
    processed = succeeded + conflict + failed
    if processed < requested:
        return "processing" if processed else "queued"
    return "completed" if conflict == 0 and failed == 0 else "completed_with_errors"


class VolunteerBatchService:
    def __init__(self, repository: VolunteerAccessRepository) -> None:
        self.repository = repository

    @staticmethod
    def chunks(items: Sequence[T]) -> list[list[T]]:
        return list(chunk_targets(items))

    @staticmethod
    def validate_operation_replay(batch: Any, fingerprint: str):
        if batch.request_fingerprint != fingerprint:
            raise DomainError(
                "operation_payload_conflict",
                "相同 operation id 不可使用不同批次內容",
                409,
            )
        return batch

    async def create_snapshot(
        self,
        *,
        actor_user_id: UUID,
        operation_id: UUID,
        decision: str,
        selection_mode: str,
        explicit_items: list[tuple[UUID, int]] | None,
        filters: Mapping[str, Any] | None,
        request_payload: Mapping[str, Any],
        reason: str | None = None,
        platform_support_reason: str | None = None,
        default_valid_from: datetime | None = None,
        default_expires_at: datetime | None = None,
    ) -> tuple[VolunteerDecisionBatch, list[VolunteerDecisionBatchItem]]:
        if decision not in {"approve", "reject"}:
            raise DomainError("invalid_batch_decision", "批次決策無效", 422)
        if decision == "reject" and not (reason or "").strip():
            raise DomainError("reason_required", "拒絕必須提供原因", 422)
        fingerprint = request_fingerprint(request_payload)
        operation_lookup = getattr(self.repository, "batch_by_operation", None)
        existing = None if operation_lookup is None else await operation_lookup(operation_id)
        if existing is not None:
            return self.validate_operation_replay(existing, fingerprint), []

        snapshot_at = datetime.now(timezone.utc)
        if selection_mode == "explicit_items":
            targets = validate_explicit_items(explicit_items or [])
            raw_service_date = dict(filters or {}).get("service_date")
            service_date = (
                raw_service_date
                if raw_service_date is None or isinstance(raw_service_date, date)
                else date.fromisoformat(raw_service_date)
            )
            await self.repository.validate_explicit_service_date_targets(
                [application_id for application_id, _ in targets],
                service_date=service_date,
            )
        elif selection_mode == "all_filtered":
            snapshot_filters = dict(filters or {})
            has_service_date = snapshot_filters.get("service_date") is not None
            has_unassigned_scope = snapshot_filters.get("unassigned") is True
            if has_service_date == has_unassigned_scope:
                raise DomainError(
                    "invalid_batch_date_scope",
                    "全選快照必須指定一個日期範圍",
                    422,
                )
            applications = await self.repository.pending_snapshot(
                snapshot_at=snapshot_at, **snapshot_filters
            )
            targets = [(application.id, application.version) for application in applications]
            if not targets:
                raise DomainError("empty_batch_selection", "目前篩選結果沒有待審核申請", 422)
        else:
            raise DomainError("invalid_selection_mode", "批次選取模式無效", 422)

        policy_version = None
        policy_duration = None
        if decision == "approve":
            policy_getter = getattr(self.repository, "policy", None)
            if policy_getter is not None:
                policy = await policy_getter()
                policy_version = policy.version
                policy_duration = effective_grant_duration_hours(policy)

        filter_snapshot = {
            key: value.isoformat() if isinstance(value, (date, datetime)) else value
            for key, value in dict(filters or {}).items()
        }

        batch = VolunteerDecisionBatch(
            id=uuid4(),
            organization_id=self.repository.organization_id,
            operation_id=operation_id,
            actor_user_id=actor_user_id,
            platform_support_reason=platform_support_reason,
            decision=decision,
            reason=(reason or "").strip() or None,
            default_valid_from=default_valid_from,
            default_expires_at=default_expires_at,
            policy_version_used=policy_version,
            default_duration_hours_used=policy_duration,
            selection_mode=selection_mode,
            filter_snapshot=filter_snapshot or None,
            snapshot_at=snapshot_at,
            request_fingerprint=fingerprint,
            status="queued",
            requested_count=len(targets),
            processed_count=0,
            succeeded_count=0,
            conflict_count=0,
            failed_count=0,
        )
        items = [
            VolunteerDecisionBatchItem(
                id=uuid4(),
                organization_id=self.repository.organization_id,
                batch_id=batch.id,
                application_id=application_id,
                expected_version=expected_version,
                result="pending",
            )
            for application_id, expected_version in targets
        ]
        await self.repository.add(batch)
        await self.repository.add_all(items)
        return batch, items

    async def process_pending_items(
        self,
        batch: VolunteerDecisionBatch,
        access_service: Any,
        *,
        limit: int = MAX_BATCH_CHUNK_SIZE,
        claimed_items: Sequence[VolunteerDecisionBatchItem] | None = None,
    ) -> VolunteerDecisionBatch:
        items = (
            list(claimed_items)
            if claimed_items is not None
            else await self.repository.pending_batch_items(batch.id, limit=limit)
        )
        batch.status = "processing"
        for item in items:
            try:
                service_date = None
                filter_snapshot = getattr(batch, "filter_snapshot", None)
                if filter_snapshot:
                    raw_service_date = filter_snapshot.get("service_date")
                    if raw_service_date:
                        service_date = (
                            raw_service_date
                            if isinstance(raw_service_date, date)
                            else date.fromisoformat(raw_service_date)
                        )
                decision_arguments = {
                    "application_id": item.application_id,
                    "expected_version": item.expected_version,
                    "decision": batch.decision,
                    "actor_user_id": batch.actor_user_id,
                    "reason": batch.reason,
                    "valid_from": item.override_valid_from or batch.default_valid_from,
                    "expires_at": item.override_expires_at or batch.default_expires_at,
                    "policy_version_used": batch.policy_version_used,
                    "duration_hours_used": batch.default_duration_hours_used,
                    "operation_id": getattr(batch, "operation_id", None),
                    "service_date": service_date,
                }
                session = getattr(self.repository, "session", None)
                if session is None:
                    application, membership, grant = await access_service.decide_application(
                        **decision_arguments
                    )
                else:
                    async with session.begin_nested():
                        application, membership, grant = await access_service.decide_application(
                            **decision_arguments
                        )
                        await session.flush()
                item.result = "succeeded"
                item.resulting_application_version = application.version
                item.membership_id = None if membership is None else membership.id
                item.grant_id = None if grant is None else grant.id
            except DomainError as exc:
                item.result = "conflict" if exc.status_code in {404, 409} else "failed"
                item.error_code = exc.code
            except Exception:
                item.result = "failed"
                item.error_code = "internal_processing_error"
            item.processed_at = datetime.now(timezone.utc)
        counts = await self.repository.reconcile_batch_counts(batch.id)
        batch.requested_count = counts["requested"]
        batch.succeeded_count = counts["succeeded"]
        batch.conflict_count = counts["conflict"]
        batch.failed_count = counts["failed"]
        batch.processed_count = batch.succeeded_count + batch.conflict_count + batch.failed_count
        batch.status = terminal_batch_status(
            batch.requested_count,
            succeeded=batch.succeeded_count,
            conflict=batch.conflict_count,
            failed=batch.failed_count,
        )
        if batch.status in {"completed", "completed_with_errors"}:
            batch.completed_at = datetime.now(timezone.utc)
        return batch


__all__ = [
    "MAX_BATCH_CHUNK_SIZE",
    "VolunteerBatchService",
    "chunk_targets",
    "merge_decision_period",
    "terminal_batch_status",
    "validate_explicit_items",
]
