from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.care_report import CareReport
from services.api.app.persistence.models.observation import ObservationCategory, ObservationOption
from services.api.app.persistence.models.observation_usage import ObservationOptionUsage
from services.api.app.persistence.repositories.observation_usage_repository import (
    ObservationOptionUsageRepository,
)

UNOBSERVED = "unobserved"


class ObservationOptionUsageService:
    """Maintain a conservative, rebuildable index without blocking reports."""

    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id
        self.repository = ObservationOptionUsageRepository(session, organization_id)

    async def _options(self) -> dict[str, ObservationOption]:
        result = await self.session.execute(
            select(ObservationOption).where(
                (ObservationOption.organization_id.is_(None))
                | (ObservationOption.organization_id == self.organization_id)
            )
        )
        return {option.code: option for option in result.scalars()}

    async def _category_codes(self) -> dict[UUID, str]:
        result = await self.session.execute(
            select(ObservationCategory).where(
                or_(
                    ObservationCategory.organization_id.is_(None),
                    ObservationCategory.organization_id == self.organization_id,
                )
            )
        )
        return {category.id: category.code for category in result.scalars()}

    @staticmethod
    def _snapshot_value(
        field: str,
        code: str,
        snapshots: Mapping[str, Any] | None,
        options: Mapping[str, ObservationOption],
        category_codes: Mapping[UUID, str],
    ) -> tuple[str, str | None, str | None, UUID | None]:
        snapshot = snapshots.get(field) if snapshots else None
        if isinstance(snapshot, Mapping):
            snapshot_code = str(snapshot.get("code") or snapshot.get("stable_code") or code)
            category = snapshot.get("category_code")
            display_name = snapshot.get("display_name")
            description = snapshot.get("description")
        else:
            snapshot_code = code
            category = None
            display_name = None
            description = None
        option = options.get(snapshot_code)
        category = str(
            category
            or (category_codes.get(option.category_id) if option else None)
            or snapshot_code.split(".", 1)[0]
        )
        return (
            category,
            (
                str(display_name)
                if display_name is not None
                else option.display_name
                if option
                else None
            ),
            (
                str(description)
                if description is not None
                else option.description
                if option
                else None
            ),
            option.id if option else None,
        )

    async def index_report(
        self,
        report: CareReport,
        *,
        answers: Mapping[str, Any] | None = None,
        snapshots: Mapping[str, Any] | None = None,
    ) -> list[ObservationOptionUsage]:
        if report.organization_id != self.organization_id:
            raise ValueError("observation usage scope mismatch")
        options = await self._options()
        category_codes = await self._category_codes()
        values = answers if answers is not None else report.answers
        snapshot_values = snapshots or report.answer_snapshots or {}
        fields = set(values) | set(snapshot_values)
        created: list[ObservationOptionUsage] = []
        for field in fields:
            raw_code = values.get(field)
            snapshot = snapshot_values.get(field)
            snapshot_code = (
                snapshot.get("code") or snapshot.get("stable_code")
                if isinstance(snapshot, Mapping)
                else None
            )
            option_code = raw_code if isinstance(raw_code, str) and raw_code else snapshot_code
            if not isinstance(option_code, str) or not option_code:
                continue
            if option_code == UNOBSERVED:
                continue
            category, display_name, description, option_id = self._snapshot_value(
                field, option_code, snapshot_values, options, category_codes
            )
            existing = await self.session.execute(
                select(ObservationOptionUsage).where(
                    ObservationOptionUsage.organization_id == self.organization_id,
                    ObservationOptionUsage.care_report_id == report.id,
                    ObservationOptionUsage.option_code == option_code,
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue
            usage = ObservationOptionUsage(
                organization_id=self.organization_id,
                care_report_id=report.id,
                observation_option_id=option_id,
                category_code=category,
                option_code=option_code,
                display_name=display_name,
                description=description,
            )
            self.session.add(usage)
            created.append(usage)
        if created:
            await self.session.flush()
        return created

    async def has_usage(self, option_id: UUID) -> bool:
        return await self.repository.has_usage(option_id)

    async def count(self, option_id: UUID) -> int:
        return await self.repository.count_for_option(option_id)

    async def rebuild_report(self, report: CareReport) -> list[ObservationOptionUsage]:
        if report.organization_id != self.organization_id:
            raise ValueError("observation usage scope mismatch")
        await self.repository.clear_for_report(report.id)
        return await self.index_report(
            report,
            answers=report.answers,
            snapshots=report.answer_snapshots,
        )

    async def rebuild_all(self) -> int:
        result = await self.session.execute(
            select(CareReport).where(CareReport.organization_id == self.organization_id)
        )
        reports = list(result.scalars())
        for report in reports:
            await self.rebuild_report(report)
        return len(reports)
