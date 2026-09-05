"""Seed one walk report that matches what the LINE flow actually stores.

The demo seeds predate the frozen six-question walk vocabulary, so every
report they create carries option codes that no longer exist in
observation_options (care_completion.*, feeding.*, water.* ...). Reviewing
the report inbox against that data shows codes the vocabulary cannot name.

This seeds a report the LINE bot would produce today: the six required
answers from the current vocabulary, with answer_snapshots built by the same
helper the bot uses, so the management UI resolves every row to its Chinese
label.

Re-running is safe — the fixed idempotency key returns the existing report.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from scripts.local_demo import guard
from services.api.app.application.audit_service import AuditService
from services.api.app.application.effective_observation_service import (
    EffectiveObservationService,
    EffectiveOption,
)

# The bot's snapshot builder is private, but duplicating it here would let the
# seed drift from the wording real reports capture — the whole point of this
# fixture. Importing it keeps the two in lockstep.
from services.api.app.application.line_draft_conversation import _build_answer_snapshots
from services.api.app.application.observation_option_usage_service import (
    ObservationOptionUsageService,
)
from services.api.app.application.report_submission import ReportSubmissionService
from services.api.app.domain.line_care_report_state import REQUIRED_ANSWER_KEYS, UNOBSERVED
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.care_report_draft import CareReportDraft
from services.api.app.persistence.models.identity import Organization, OrganizationMembership, User
from services.api.app.persistence.repositories.care_report_draft_repository import (
    CareReportDraftRepository,
    draft_token_digest,
)
from services.api.app.persistence.repositories.care_report_repository import CareReportRepository
from services.api.app.persistence.repositories.observation_repository import ObservationRepository
from sqlalchemy import select

ORGANIZATION_CODE = "FURKIDS-ASIA"
ANIMAL_SHELTER_NUMBER = "MTF-20140531-001"  # 獒黃妹
VOLUNTEER_USERNAME = "demo-furkids-volunteer"
IDEMPOTENCY_KEY = "seed-walk-report-example-v1"
DAYS_AGO = 1

# A walk that went less than perfectly, so the inbox shows six distinct
# labels rather than six repetitions of 正常.
#
# appearance_special_status is the sentinel rather than an appearance.* code
# because that question currently offers zero options in the LINE flow: the
# category is appearance_special_status while its codes are appearance.*, and
# EffectiveObservationService.is_valid requires the code to be prefixed with
# the category. Until that is reconciled, "unobserved" is what a real walk
# report carries for this question.
ANSWERS = {
    "walk_completion": "walk_completion.partially_completed",
    "activity": "activity.lower",
    "gait": "gait.off",
    "defecation": "defecation.soft",
    "animal_interaction": "animal_interaction.wary",
    "appearance_special_status": UNOBSERVED,
}
NOTE = "走到一半就不太想走，右後腳看起來有點卡，回程改用抱的。"


async def seed() -> dict[str, object]:
    guard()
    assert set(ANSWERS) == set(REQUIRED_ANSWER_KEYS), "answers must cover the required keys"
    async with session_factory() as session, session.begin():
        organization = (
            await session.execute(
                select(Organization).where(Organization.code == ORGANIZATION_CODE)
            )
        ).scalar_one()
        await set_organization_scope(session, organization.id)

        animal = (
            await session.execute(
                select(Animal).where(
                    Animal.organization_id == organization.id,
                    Animal.shelter_number == ANIMAL_SHELTER_NUMBER,
                )
            )
        ).scalar_one()
        volunteer, membership = (
            await session.execute(
                select(User, OrganizationMembership)
                .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
                .where(
                    User.username == VOLUNTEER_USERNAME,
                    OrganizationMembership.organization_id == organization.id,
                )
            )
        ).one()

        reports = CareReportRepository(session, organization.id)
        existing = await reports.get_idempotent(volunteer_user_id=volunteer.id, key=IDEMPOTENCY_KEY)
        if existing is not None:
            return {"report_id": str(existing.id), "created": False}

        options = await ObservationRepository(session, organization.id).effective_options(
            include_disabled_history=False
        )
        service = EffectiveObservationService(
            {
                option.code: EffectiveOption(
                    code=option.code,
                    display_name=option.display_name,
                    description=option.description,
                    requires_note=option.requires_note,
                    active=option.status == "active",
                )
                for option in options
            }
        )

        now = datetime.now(timezone.utc)
        drafts = CareReportDraftRepository(session, organization.id)
        draft = CareReportDraft(
            id=uuid4(),
            opaque_token_digest=draft_token_digest(secrets.token_urlsafe(32)),
            organization_id=organization.id,
            volunteer_user_id=volunteer.id,
            membership_id=membership.id,
            animal_id=animal.id,
            current_step="reviewing",
            answers=dict(ANSWERS),
            note=NOTE,
            status="active",
            last_interaction_at=now,
            expires_at=now + timedelta(hours=2),
        )
        session.add(draft)
        await session.flush()

        report = await ReportSubmissionService(
            drafts,
            reports,
            answer_validator=service.validate_answer,
            audit=AuditService(session),
            note_validator=service.validate_note_requirement,
            answer_snapshots=await _build_answer_snapshots(session, organization.id, dict(ANSWERS)),
            usage_service=ObservationOptionUsageService(session, organization.id),
        ).submit(
            draft_id=draft.id,
            volunteer_user_id=volunteer.id,
            animal=animal,
            idempotency_key=IDEMPOTENCY_KEY,
            note=NOTE,
        )
        # Dated deliberately so the animal timeline shows more than one day.
        report.submitted_at = now - timedelta(days=DAYS_AGO)
        return {
            "report_id": str(report.id),
            "created": True,
            "animal": report.animal_name_snapshot,
            "answers": {
                field: snapshot["display_name"]
                for field, snapshot in (report.answer_snapshots or {}).items()
            },
        }


def main() -> None:
    import json

    print(json.dumps(asyncio.run(seed()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
