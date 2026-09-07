"""Seed AIProcessingJob + AIObservation demo rows for tweaking the AI 人工覆核 UI.

Populates a handful of ai_observations rows across every status the ai-review
page renders, attached to existing FURKIDS-ASIA demo care reports, so the page
is not empty while iterating on its layout. Local dev database only.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid5

from services.api.app.domain.report_summary import fingerprint, rule_summary
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.ai_observation import AIObservation
from services.api.app.persistence.models.care_report import CareReport
from services.api.app.persistence.models.identity import Organization
from sqlalchemy import select

ORGANIZATION_CODE = "FURKIDS-ASIA"
UI_DEMO_NAMESPACE = UUID("6f2a3e9d-6c9a-4a1e-8e63-9a2f2c1d9b30")


def stable_id(kind: str, key: str) -> UUID:
    return uuid5(UI_DEMO_NAMESPACE, f"{kind}:{key}")


# report_index is a permanent, hand-assigned slot into the id-ordered list of
# FURKIDS-ASIA care_reports. It must never be inferred from list position/order
# (e.g. via zip or sorting), because uq_ai_job_target_version means reassigning
# an existing key to a different report collides with whatever job already
# owns that report. To add a scenario, append it with the next unused index;
# never change an existing scenario's index.
SCENARIOS = [
    {"key": "pending", "status": "pending", "failure_reason": None, "report_index": 0},
    {"key": "succeeded", "status": "succeeded", "failure_reason": None, "report_index": 1},
    {"key": "failed", "status": "failed", "failure_reason": "AI 服務逾時無回應", "report_index": 2},
    {
        "key": "invalid",
        "status": "invalid",
        "failure_reason": "AI 輸出格式驗證失敗",
        "report_index": 3,
    },
    {"key": "confirmed", "status": "confirmed", "failure_reason": None, "report_index": 4},
    {"key": "rejected", "status": "rejected", "failure_reason": None, "report_index": 5},
    {"key": "corrected", "status": "corrected", "failure_reason": None, "report_index": 6},
    {"key": "succeeded-2", "status": "succeeded", "failure_reason": None, "report_index": 7},
    {"key": "succeeded-3", "status": "succeeded", "failure_reason": None, "report_index": 8},
    {"key": "succeeded-4", "status": "succeeded", "failure_reason": None, "report_index": 9},
    {"key": "succeeded-5", "status": "succeeded", "failure_reason": None, "report_index": 10},
    {"key": "succeeded-6", "status": "succeeded", "failure_reason": None, "report_index": 11},
]


async def seed() -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with session_factory() as session:
        async with session.begin():
            organization = (
                await session.execute(
                    select(Organization).where(Organization.code == ORGANIZATION_CODE)
                )
            ).scalar_one_or_none()
            if organization is None:
                raise RuntimeError(
                    f"Organization '{ORGANIZATION_CODE}' not found; "
                    "run scripts/seed_furkids_demo.py first."
                )

            report_count = max(scenario["report_index"] for scenario in SCENARIOS) + 1
            reports = (
                (
                    await session.execute(
                        select(CareReport)
                        .where(CareReport.organization_id == organization.id)
                        .order_by(CareReport.id)
                        .limit(report_count)
                    )
                )
                .scalars()
                .all()
            )
            if len(reports) < report_count:
                raise RuntimeError(
                    "Not enough care_reports for FURKIDS-ASIA to attach demo AI observations; "
                    "run scripts/seed_furkids_demo.py first."
                )

            created_or_updated = 0
            for scenario in SCENARIOS:
                report = reports[scenario["report_index"]]
                # The review endpoint refuses to confirm/reject/correct an
                # AIObservation whose care_report_summary source no longer
                # matches the report's current content-hash fingerprint. Set
                # it here so these demo rows are actually reviewable in the UI.
                report.summary_fingerprint = fingerprint(report)
                report.summary_status = "succeeded"

                job_id = stable_id("ai-job", scenario["key"])
                job = await session.get(AIProcessingJob, job_id)
                if job is None:
                    job = AIProcessingJob(id=job_id, organization_id=organization.id)
                    session.add(job)
                job.job_type = "care_observation"
                job.target_type = "care_report"
                job.target_id = report.id
                # Keep the job itself in a terminal (non-claimable) state so the
                # local worker (services.worker.worker) never picks it up and
                # overwrites this fixture with a real processing result. The
                # ai-review page reads AIObservation.status, not the job's.
                job.status = "failed" if scenario["status"] == "failed" else "succeeded"
                job.provider = "local-fixture"
                job.model_name = "local-fixture-model"
                job.model_version = "ui-demo-v1"
                job.prompt_template_id = "care-observation"
                job.prompt_version = "ui-demo-v1"
                job.output_schema_version = "ui-demo-v1"
                job.raw_ai_output = {"note": f"UI demo fixture for status={scenario['status']}"}
                job.validation_result = None
                job.failure_reason = scenario["failure_reason"]
                job.completed_at = now - timedelta(hours=1)
                job.updated_at = now

                observation_id = stable_id("ai-observation", scenario["key"])
                observation = await session.get(AIObservation, observation_id)
                if observation is None:
                    observation = AIObservation(id=observation_id, organization_id=organization.id)
                    session.add(observation)
                observation.job_id = job.id
                observation.source_type = "care_report_summary"
                observation.source_id = report.id
                observation.status = scenario["status"]
                observation.raw_ai_output = job.raw_ai_output
                observation.validated_ai_observation = (
                    {
                        **rule_summary(report),
                        "summary": f"（示範資料）{scenario['status']} 狀態的 AI 摘要內容",
                    }
                    if scenario["status"] not in {"failed", "invalid", "pending"}
                    else None
                )
                observation.human_review_result = (
                    {"reason": f"（示範資料）人工覆核備註 - {scenario['status']}"}
                    if scenario["status"] in {"confirmed", "rejected", "corrected"}
                    else None
                )
                observation.updated_at = now
                await session.flush()
                created_or_updated += 1
            return created_or_updated


def main() -> None:
    count = asyncio.run(seed())
    print(f"Organization: {ORGANIZATION_CODE}")
    print(f"AI observations created/updated: {count}")


if __name__ == "__main__":
    main()
