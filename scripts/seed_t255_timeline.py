"""Seed deterministic fictional Timeline data for T255 usability testing."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid5

from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.ai_observation import AIObservation
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.care_report import CareReport
from services.api.app.persistence.models.identity import (
    Organization,
    OrganizationMembership,
    User,
)
from sqlalchemy import select

ORGANIZATION_CODE = "ORG-A"
ANIMAL_SHELTER_NUMBER = "VAAAG114080610"
VOLUNTEER_USERNAME = "local-volunteer-a"
T255_NAMESPACE = UUID("9f0e9f3f-4c8e-4f73-9f32-2a6e4f4d8f04")


@dataclass(frozen=True)
class TimelineFixture:
    key: str
    days_ago: int
    hour: int
    note: str
    answer_overrides: Mapping[str, str] = field(default_factory=dict)
    ai_job_status: str = "succeeded"


NORMAL_ANSWERS: dict[str, str] = {
    "care_completion": "care_completion.completed",
    "walk_completion": "walk_completion.completed",
    "feeding": "feeding.normal",
    "water": "water.observed",
    "activity": "activity.usual",
    "urination": "urination.observed",
    "defecation": "defecation.formed",
    "resource_guarding": "resource_guarding.not_observed",
    "human_interaction": "human_interaction.usual",
    "animal_interaction": "animal_interaction.usual",
    "emotion": "emotion.calm",
    "walk_reaction": "walk.willing",
    "appearance_special_status": "appearance.not_observed",
}


FIXTURE_SPECS: tuple[TimelineFixture, ...] = (
    TimelineFixture("normal-13", 13, 9, "T255 固定資料：一般回報 13 日前"),
    TimelineFixture("normal-12", 12, 9, "T255 固定資料：一般回報 12 日前"),
    TimelineFixture("normal-11", 11, 9, "T255 固定資料：一般回報 11 日前"),
    # 10 days ago intentionally has no report for SC-014.
    TimelineFixture("normal-9", 9, 9, "T255 固定資料：一般回報 9 日前"),
    TimelineFixture("normal-8", 8, 9, "T255 固定資料：一般回報 8 日前"),
    TimelineFixture(
        "unobserved-7",
        7,
        9,
        "T255 固定資料：未觀察 7 日前",
        answer_overrides={
            "urination": "urination.not_observed",
            "defecation": "defecation.not_observed",
            "emotion": "emotion.not_observed",
        },
    ),
    TimelineFixture("normal-6", 6, 9, "T255 固定資料：一般回報 6 日前"),
    TimelineFixture("normal-5", 5, 9, "T255 固定資料：一般回報 5 日前"),
    TimelineFixture(
        "uncertain-4",
        4,
        9,
        "T255 固定資料：無法判斷 4 日前",
        answer_overrides={
            "urination": "urination.uncertain",
            "defecation": "defecation.uncertain",
            "emotion": "emotion.uncertain",
        },
    ),
    TimelineFixture("normal-3", 3, 9, "T255 固定資料：一般回報 3 日前"),
    TimelineFixture(
        "ai-failed-2",
        2,
        9,
        "T255 固定資料：AI 處理失敗 2 日前",
        ai_job_status="failed",
    ),
    TimelineFixture("same-day-1-morning", 1, 9, "T255 固定資料：同日第一筆回報"),
    TimelineFixture("same-day-1-evening", 1, 17, "T255 固定資料：同日第二筆回報"),
    TimelineFixture("normal-0", 0, 9, "T255 固定資料：一般回報今日"),
)


DISPLAY_NAMES = {
    "not_observed": "未觀察",
    "uncertain": "無法判斷",
}


def build_fixture_answers(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    answers = dict(NORMAL_ANSWERS)
    answers.update(overrides or {})
    return answers


def build_answer_snapshots(answers: Mapping[str, str]) -> dict[str, dict[str, str]]:
    snapshots: dict[str, dict[str, str]] = {}
    for key, code in answers.items():
        option = code.rsplit(".", 1)[-1]
        snapshots[key] = {
            "code": code,
            "display_name": DISPLAY_NAMES.get(option, option),
        }
    return snapshots


def stable_id(kind: str, key: str, target_id: UUID) -> UUID:
    return uuid5(T255_NAMESPACE, f"{kind}:ORG-A:{target_id}:{key}")


async def _required_records(session) -> tuple[Organization, Animal, User, OrganizationMembership]:
    organization = await session.scalar(
        select(Organization).where(Organization.code == ORGANIZATION_CODE)
    )
    if organization is None:
        raise RuntimeError("找不到 ORG-A，請先執行：uv run python -m scripts.seed_local")

    animal = await session.scalar(
        select(Animal).where(
            Animal.organization_id == organization.id,
            Animal.shelter_number == ANIMAL_SHELTER_NUMBER,
        )
    )
    volunteer = await session.scalar(select(User).where(User.username == VOLUNTEER_USERNAME))
    if animal is None or volunteer is None:
        raise RuntimeError("找不到本機動物或志工，請先執行：uv run python -m scripts.seed_local")

    membership = await session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == volunteer.id,
            OrganizationMembership.status == "active",
        )
    )
    if membership is None:
        raise RuntimeError(
            "找不到 ORG-A 志工 Membership，請先執行：uv run python -m scripts.seed_local"
        )
    return organization, animal, volunteer, membership


async def _upsert_failed_ai_trace(
    session,
    *,
    organization_id: UUID,
    report: CareReport,
    now: datetime,
) -> None:
    job_id = stable_id("ai-job", report.id.hex, report.id)
    job = await session.get(AIProcessingJob, job_id)
    if job is None:
        job = AIProcessingJob(id=job_id, organization_id=organization_id)
        session.add(job)
    job.job_type = "care_observation"
    job.target_type = "care_report"
    job.target_id = report.id
    job.status = "failed"
    job.provider = "local-fixture"
    job.model_name = "local-fixture-model"
    job.model_version = "t255-v1"
    job.prompt_template_id = "care-observation"
    job.prompt_version = "t255-v1"
    job.output_schema_version = "t255-v1"
    job.raw_ai_output = None
    job.validation_result = {"status": "failed", "error_code": "fixture_ai_failure"}
    job.failure_reason = "fixture_ai_failure"
    job.retry_count = 1
    job.completed_at = now
    job.updated_at = now

    observation_id = stable_id("ai-observation", report.id.hex, report.id)
    observation = await session.get(AIObservation, observation_id)
    if observation is None:
        observation = AIObservation(id=observation_id, organization_id=organization_id)
        session.add(observation)
    observation.job_id = job.id
    observation.source_type = "note"
    observation.source_id = report.id
    observation.status = "failed"
    observation.raw_ai_output = None
    observation.validated_ai_observation = None
    observation.human_review_result = None
    observation.updated_at = now


async def seed_timeline() -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with session_factory() as session:
        async with session.begin():
            organization, animal, volunteer, membership = await _required_records(session)
            created_or_updated = 0
            for spec in FIXTURE_SPECS:
                report_id = stable_id("report", spec.key, animal.id)
                submitted_at = (now - timedelta(days=spec.days_ago)).replace(
                    hour=spec.hour, minute=0, second=0, microsecond=0
                )
                answers = build_fixture_answers(spec.answer_overrides)
                report = await session.get(CareReport, report_id)
                if report is None:
                    report = CareReport(id=report_id, organization_id=organization.id)
                    session.add(report)
                report.draft_id = None
                report.animal_id = animal.id
                report.volunteer_user_id = volunteer.id
                report.membership_id = membership.id
                report.answers = answers
                report.answer_snapshots = build_answer_snapshots(answers)
                report.animal_name_snapshot = animal.name
                report.shelter_number_snapshot = animal.shelter_number
                report.note = spec.note
                report.status = "saved"
                report.ai_job_status = spec.ai_job_status
                report.submitted_at = submitted_at
                report.updated_at = now
                await session.flush()
                if spec.ai_job_status == "failed":
                    await _upsert_failed_ai_trace(
                        session,
                        organization_id=organization.id,
                        report=report,
                        now=now,
                    )
                created_or_updated += 1
            return created_or_updated


def main() -> None:
    count = asyncio.run(seed_timeline())
    print(f"已建立／更新 T255 Timeline 固定回報：{count} 筆")
    print(f"Organization：{ORGANIZATION_CODE}")
    print(f"Animal shelter number：{ANIMAL_SHELTER_NUMBER}")
    print("10 日前刻意保留為無回報日；2 日前為 AI failed；1 日前有同日兩筆回報。")


if __name__ == "__main__":
    main()
