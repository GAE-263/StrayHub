from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.domain.care_recurrence import (
    nth_local,
    occurrence_at,
    occurrence_id,
    validate_frequency,
)
from services.api.app.domain.care_reminder_state import decide_reminder_action
from services.api.app.domain.organization_timezone import local_to_utc
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.identity import Organization, OrganizationMembership
from services.api.app.persistence.models.medical_care import (
    CareReminderAction,
    CareReminderOccurrence,
    CareReminderSeries,
)
from services.api.app.persistence.repositories.care_reminder_repository import (
    CareReminderRepository,
)


class CareReminderService:
    def __init__(self, session: AsyncSession, context: RequestContext) -> None:
        self.session, self.context = session, context
        if context.organization_id is None:
            raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
        self.organization_id = context.organization_id

    async def organization(self) -> Organization:
        org = (
            await self.session.execute(
                select(Organization).where(Organization.id == self.organization_id)
            )
        ).scalar_one_or_none()
        if org is None:
            raise DomainError("organization_not_found", "收容所不存在", 404)
        return org

    async def _replay_action(
        self,
        repo: CareReminderRepository,
        *,
        idempotency_key: str,
        fingerprint: str,
    ) -> ReminderActionResult | None:
        prior_action = await repo.action_by_idempotency(
            actor_user_id=self.context.user_id, idempotency_key=idempotency_key
        )
        if prior_action is None:
            return None
        if prior_action.request_fingerprint != fingerprint:
            raise DomainError("idempotency_key_reused", "相同 Idempotency-Key 的內容不同", 409)
        prior = await repo.occurrence(prior_action.occurrence_id)
        if prior is None:
            raise DomainError("occurrence_not_found", "提醒項目不存在或無法存取", 404)
        return ReminderActionResult(prior, prior_action)

    async def create_series(self, animal_id: UUID, data: dict) -> CareReminderSeries:
        animal = (
            await self.session.execute(
                select(Animal).where(
                    Animal.id == animal_id, Animal.organization_id == self.organization_id
                )
            )
        ).scalar_one_or_none()
        if animal is None:
            raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
        if animal.status != "active":
            raise DomainError("animal_not_active", "非在養動物不可建立新提醒", 422)
        validate_frequency(data["frequency"], data["interval"])
        if data.get("assignee_membership_id") is not None:
            now = datetime.now(timezone.utc)
            membership = (
                await self.session.execute(
                    select(OrganizationMembership).where(
                        OrganizationMembership.id == data["assignee_membership_id"],
                        OrganizationMembership.organization_id == self.organization_id,
                        OrganizationMembership.status == "active",
                        OrganizationMembership.role.in_(["SHELTER_ADMIN", "STAFF", "VOLUNTEER"]),
                        (
                            OrganizationMembership.valid_from.is_(None)
                            | (OrganizationMembership.valid_from <= now)
                        ),
                        (
                            OrganizationMembership.expires_at.is_(None)
                            | (OrganizationMembership.expires_at > now)
                        ),
                    )
                )
            ).scalar_one_or_none()
            if membership is None:
                raise DomainError("assignee_invalid", "負責人不屬於目前收容所或已停用", 422)
        series = CareReminderSeries(
            organization_id=self.organization_id,
            lineage_id=uuid4(),
            animal_id=animal_id,
            reminder_type=data["reminder_type"],
            title=data["title"].strip(),
            instructions=data.get("instructions", "").strip(),
            assignee_membership_id=data.get("assignee_membership_id"),
            anchor_local_date=data["anchor_local_date"],
            anchor_local_time=data["anchor_local_time"],
            frequency=data["frequency"],
            interval=data["interval"],
            end_local_date=data.get("end_local_date"),
            created_by_user_id=self.context.user_id,
            updated_by_user_id=self.context.user_id,
        )
        if series.end_local_date and series.end_local_date < series.anchor_local_date:
            raise DomainError("invalid_end_date", "結束日期不可早於第一次執行日期", 422)
        self.session.add(series)
        await self.session.flush()
        await AuditService(self.session).record(
            organization_id=self.organization_id,
            actor_user_id=self.context.user_id,
            action="care_reminder_series.created",
            resource_type="CareReminderSeries",
            resource_id=series.id,
            source_channel="api",
            after=series,
        )
        await self.session.commit()
        return series

    async def stop_series(
        self, series_id: UUID, expected_version: int, reason: str
    ) -> CareReminderSeries:
        series = await CareReminderRepository(self.session, self.organization_id).series(
            series_id, for_update=True
        )
        if series is None:
            raise DomainError("reminder_series_not_found", "提醒不存在或無法存取", 404)
        if series.version != expected_version or series.status == "stopped":
            raise DomainError("reminder_series_version_conflict", "提醒已更新，請重新載入", 409)
        series.status = "stopped"
        series.version += 1
        series.stopped_at = datetime.now(timezone.utc)
        series.stopped_by_user_id = self.context.user_id
        series.stop_reason = reason
        await AuditService(self.session).record(
            organization_id=self.organization_id,
            actor_user_id=self.context.user_id,
            action="care_reminder_series.stopped",
            resource_type="CareReminderSeries",
            resource_id=series.id,
            source_channel="api",
            reason=reason,
        )
        await self.session.commit()
        return series

    async def resolve_occurrence(
        self, occurrence_id_value: UUID
    ) -> tuple[CareReminderSeries, int, date, datetime]:
        repo = CareReminderRepository(self.session, self.organization_id)
        persisted = await repo.occurrence(occurrence_id_value)
        if persisted:
            series = await repo.series(persisted.series_id)
            if series is None:
                raise DomainError("occurrence_not_found", "提醒項目不存在或無法存取", 404)
            return (
                series,
                persisted.occurrence_index,
                persisted.nominal_local_date,
                persisted.scheduled_at,
            )
        for series in await repo.list_series():
            for index in range(0, 367):
                if index < series.start_ordinal:
                    continue
                if series.end_ordinal is not None and index > series.end_ordinal:
                    break
                if occurrence_id(series.lineage_id, index) != occurrence_id_value:
                    continue
                day = nth_local(series.anchor_local_date, series.frequency, series.interval, index)
                if series.end_local_date and day > series.end_local_date:
                    break
                return (
                    series,
                    index,
                    day,
                    occurrence_at(
                        series.anchor_local_date,
                        series.anchor_local_time,
                        series.frequency,
                        series.interval,
                        index,
                        (await self.organization()).timezone,
                    ),
                )
        raise DomainError("occurrence_not_found", "提醒項目不存在或無法存取", 404)

    async def edit_occurrence(
        self,
        occurrence_id_value: UUID,
        *,
        scope: str,
        expected_version: int,
        scheduled_at: datetime | None,
        title: str | None,
        instructions: str | None,
        reason: str,
        idempotency_key: str,
    ) -> CareReminderOccurrence:
        """Edit one virtual occurrence or split a series from this occurrence onward."""
        if scope not in {"this", "this_and_future"}:
            raise DomainError("invalid_edit_scope", "請選擇本次或本次及未來", 422)
        fingerprint = sha256(
            f"edit:{occurrence_id_value}:{scope}:{expected_version}:{scheduled_at}:{title}:{instructions}:{reason}".encode()
        ).hexdigest()
        repo = CareReminderRepository(self.session, self.organization_id)
        prior_action = await repo.action_by_idempotency(
            actor_user_id=self.context.user_id, idempotency_key=idempotency_key
        )
        if prior_action is not None:
            if prior_action.request_fingerprint != fingerprint:
                raise DomainError("idempotency_key_reused", "相同 Idempotency-Key 的內容不同", 409)
            prior = await repo.occurrence(prior_action.occurrence_id)
            if prior is not None:
                return prior

        org = await self.organization()
        series, index, nominal_day, original_scheduled_at = await self.resolve_occurrence(
            occurrence_id_value
        )
        if series.status != "active":
            raise DomainError("reminder_not_active", "提醒目前已停止或暫停", 409)
        existing = await repo.occurrence(occurrence_id_value, for_update=True)
        if existing is not None:
            if existing.version != expected_version:
                raise DomainError("occurrence_version_conflict", "提醒已更新，請重新載入", 409)
            if existing.status != "pending":
                raise DomainError("occurrence_terminal", "已完成或結束的提醒不可修改", 409)
        if scope == "this_and_future":
            if index <= series.start_ordinal:
                target = series
                if title is not None:
                    target.title = title.strip()
                if instructions is not None:
                    target.instructions = instructions.strip()
                if scheduled_at is not None:
                    local_scheduled = (
                        scheduled_at.replace(tzinfo=ZoneInfo(org.timezone))
                        if scheduled_at.tzinfo is None
                        else scheduled_at.astimezone(ZoneInfo(org.timezone))
                    )
                    target.anchor_local_time = local_scheduled.time().replace(tzinfo=None)
                target.version += 1
                target.updated_by_user_id = self.context.user_id
            else:
                old_end = series.end_ordinal
                series.end_ordinal = index - 1
                series.version += 1
                series.updated_by_user_id = self.context.user_id
                target = CareReminderSeries(
                    organization_id=self.organization_id,
                    lineage_id=series.lineage_id,
                    supersedes_series_id=series.id,
                    animal_id=series.animal_id,
                    reminder_type=series.reminder_type,
                    title=title.strip() if title is not None else series.title,
                    instructions=instructions.strip()
                    if instructions is not None
                    else series.instructions,
                    assignee_membership_id=series.assignee_membership_id,
                    anchor_local_date=series.anchor_local_date,
                    anchor_local_time=series.anchor_local_time,
                    start_ordinal=index,
                    end_ordinal=old_end,
                    frequency=series.frequency,
                    interval=series.interval,
                    end_local_date=series.end_local_date,
                    created_by_user_id=self.context.user_id,
                    updated_by_user_id=self.context.user_id,
                )
                if scheduled_at is not None:
                    local_scheduled = (
                        scheduled_at.replace(tzinfo=ZoneInfo(org.timezone))
                        if scheduled_at.tzinfo is None
                        else scheduled_at.astimezone(ZoneInfo(org.timezone))
                    )
                    target.anchor_local_time = local_scheduled.time().replace(tzinfo=None)
                self.session.add(target)
                await self.session.flush()
        else:
            target = series

        if existing is None:
            existing = CareReminderOccurrence(
                id=occurrence_id_value,
                organization_id=self.organization_id,
                lineage_id=series.lineage_id,
                series_id=target.id,
                occurrence_index=index,
                nominal_local_date=nominal_day,
                nominal_local_time=target.anchor_local_time,
                original_scheduled_at=original_scheduled_at,
                scheduled_at=original_scheduled_at,
                effective_timezone=org.timezone,
                timezone_version=org.timezone_version,
                status="pending",
                assignee_membership_id=target.assignee_membership_id,
                title_snapshot=target.title,
                instructions_snapshot=target.instructions,
                type_snapshot=target.reminder_type,
            )
            existing, created = await repo.add_occurrence_race_safe(existing)
            if not created:
                if existing.status != "pending" or existing.version != expected_version:
                    raise DomainError(
                        "occurrence_version_conflict", "提醒已被其他人更新，請重新載入", 409
                    )
        if title is not None:
            existing.title_snapshot = title.strip()
        elif scope == "this_and_future":
            existing.title_snapshot = target.title
        if instructions is not None:
            existing.instructions_snapshot = instructions.strip()
        elif scope == "this_and_future":
            existing.instructions_snapshot = target.instructions
        if scheduled_at is not None:
            existing.scheduled_at = local_to_utc(scheduled_at, org.timezone)
        existing.version += 1
        now = datetime.now(timezone.utc)
        existing.last_action_at = now
        existing.last_action_by_user_id = self.context.user_id
        action_row = CareReminderAction(
            organization_id=self.organization_id,
            occurrence_id=existing.id,
            lineage_id=series.lineage_id,
            series_id=target.id,
            occurrence_index=index,
            action_type="rescheduled" if scheduled_at is not None else "created_override",
            actor_user_id=self.context.user_id,
            acted_at=now,
            before_state={"scheduled_at": original_scheduled_at.isoformat()},
            after_state={"scheduled_at": existing.scheduled_at.isoformat(), "scope": scope},
            reason=reason,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
        )
        await repo.add_action(action_row)
        await AuditService(self.session).record(
            organization_id=self.organization_id,
            actor_user_id=self.context.user_id,
            action="care_reminder.edited",
            resource_type="CareReminderOccurrence",
            resource_id=existing.id,
            source_channel="api",
            reason=reason,
            after={"scope": scope, "series_id": str(target.id)},
        )
        await self.session.commit()
        return existing

    async def act(
        self,
        occurrence_id_value: UUID,
        action: str,
        reason: str | None,
        result_note: str | None,
        idempotency_key: str,
        data: dict | None = None,
        expected_version: int = 0,
    ) -> ReminderActionResult:
        org = await self.organization()
        repo = CareReminderRepository(self.session, self.organization_id)
        fingerprint = sha256(
            (
                f"{action}:{occurrence_id_value}:{reason}:{result_note}:"
                f"{(data or {}).get('scheduled_at')}:{(data or {}).get('actual_completed_at')}"
            ).encode()
        ).hexdigest()
        replay = await self._replay_action(
            repo, idempotency_key=idempotency_key, fingerprint=fingerprint
        )
        if replay is not None:
            return replay
        series, index, nominal_day, scheduled_at = await self.resolve_occurrence(
            occurrence_id_value
        )
        if series.status != "active":
            raise DomainError("reminder_not_active", "提醒目前已停止或暫停", 409)
        existing = await repo.occurrence(occurrence_id_value, for_update=True)
        if existing is not None and existing.version != expected_version:
            replay = await self._replay_action(
                repo, idempotency_key=idempotency_key, fingerprint=fingerprint
            )
            if replay is not None:
                return replay
            raise DomainError("occurrence_version_conflict", "提醒已更新，請重新載入", 409)
        now = datetime.now(timezone.utc)
        if existing is None:
            existing = CareReminderOccurrence(
                id=occurrence_id_value,
                organization_id=self.organization_id,
                lineage_id=series.lineage_id,
                series_id=series.id,
                occurrence_index=index,
                nominal_local_date=nominal_day,
                nominal_local_time=series.anchor_local_time,
                original_scheduled_at=scheduled_at,
                scheduled_at=scheduled_at,
                effective_timezone=org.timezone,
                timezone_version=org.timezone_version,
                status="pending",
                assignee_membership_id=series.assignee_membership_id,
                title_snapshot=series.title,
                instructions_snapshot=series.instructions,
                type_snapshot=series.reminder_type,
            )
            existing, created = await repo.add_occurrence_race_safe(existing)
            if not created and (
                existing.status != "pending" or existing.version != expected_version
            ):
                replay = await self._replay_action(
                    repo, idempotency_key=idempotency_key, fingerprint=fingerprint
                )
                if replay is not None:
                    return replay
                raise DomainError(
                    "occurrence_version_conflict", "提醒已被其他人更新，請重新載入", 409
                )
        before = {"status": existing.status, "scheduled_at": existing.scheduled_at.isoformat()}
        decision = decide_reminder_action(
            current_status=existing.status,
            action=action,
            recorded_at=now,
            reason=reason,
            scheduled_at=(data or {}).get("scheduled_at"),
            actual_completed_at=(data or {}).get("actual_completed_at"),
        )
        if action == "completed":
            existing.status = decision.status
            existing.actual_completed_at = decision.actual_completed_at
            existing.recorded_at = now
            existing.completed_by_user_id = self.context.user_id
            existing.result_note = result_note
        elif action in {"skipped", "cancelled"}:
            existing.status = decision.status
            existing.result_note = reason
        elif action == "rescheduled":
            existing.scheduled_at = local_to_utc((data or {})["scheduled_at"], org.timezone)
            existing.status = decision.status
        existing.version += 1
        existing.last_action_at = now
        existing.last_action_by_user_id = self.context.user_id
        after = {"status": existing.status, "scheduled_at": existing.scheduled_at.isoformat()}
        action_row = CareReminderAction(
            organization_id=self.organization_id,
            occurrence_id=existing.id,
            lineage_id=series.lineage_id,
            series_id=series.id,
            occurrence_index=index,
            action_type=action,
            actor_user_id=self.context.user_id,
            acted_at=now,
            before_state=before,
            after_state=after,
            reason=reason,
            result_note=result_note,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
        )
        await repo.add_action(action_row)
        await AuditService(self.session).record(
            organization_id=self.organization_id,
            actor_user_id=self.context.user_id,
            action=f"care_reminder.{action}",
            resource_type="CareReminderOccurrence",
            resource_id=existing.id,
            source_channel="api",
            before=before,
            after=after,
            reason=reason,
        )
        await self.session.commit()
        return ReminderActionResult(existing, action_row)


@dataclass(frozen=True)
class ReminderActionResult:
    occurrence: CareReminderOccurrence
    action: CareReminderAction
