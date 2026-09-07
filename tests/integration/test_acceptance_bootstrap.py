from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from scripts.bootstrap_acceptance import (
    ADMIN_A_USERNAME,
    ALLOWED_ENVIRONMENTS,
    ANIMAL_B_NUMBER,
    MINIMUM_PASSWORD_LENGTH,
    PASSWORD_ENV,
    PASSWORD_FILE_ENV,
    TENANT_A_CODE,
    TENANT_B_CODE,
    VOLUNTEER_A_USERNAME,
    bootstrap_acceptance,
    read_bootstrap_password,
    validate_execution_guard,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.animal_selection import (
    AnimalSelectionService,
    issue_animal_confirmation_token,
)
from services.api.app.application.authentication.session_service import SessionService
from services.api.app.application.create_report_draft import CreateReportDraftService
from services.api.app.application.report_submission import ReportSubmissionService
from services.api.app.application.volunteer_reporting_authorization import (
    VolunteerReportingAuthorizationService,
)
from services.api.app.domain.line_care_report_state import REQUIRED_ANSWER_KEYS
from services.api.app.infrastructure.auth.access_token_adapter import JwtAccessTokenAdapter
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope, set_platform_scope
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.identity import Organization, OrganizationMembership, User
from services.api.app.persistence.models.qr_code import AnimalQrCode
from services.api.app.persistence.models.reportable_scope import DailyReportableScope
from services.api.app.persistence.models.volunteer_access import VolunteerAccessGrant
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.care_report_draft_repository import (
    CareReportDraftRepository,
)
from services.api.app.persistence.repositories.care_report_repository import CareReportRepository
from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository
from services.api.app.persistence.repositories.reportable_scope_repository import (
    ReportableScopeRepository,
)
from sqlalchemy import func, select

PASSWORD = "synthetic-acceptance-password-2026"


@pytest_asyncio.fixture
async def isolated_application_database_pool() -> AsyncIterator[None]:
    await engine.dispose(close=False)
    try:
        yield
    finally:
        await engine.dispose()


def _token_adapter() -> JwtAccessTokenAdapter:
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    public = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
    return JwtAccessTokenAdapter(
        private_key=private,
        public_keys={"acceptance-test": public},
        issuer="acceptance-test",
        audience="strayhub-api",
        active_kid="acceptance-test",
    )


def test_acceptance_bootstrap_guard_fails_closed() -> None:
    for environment in ALLOWED_ENVIRONMENTS:
        assert (
            validate_execution_guard(
                app_env=environment,
                allow_value="true",
                confirmed=True,
            )
            == environment
        )
    with pytest.raises(RuntimeError, match="environment_denied"):
        validate_execution_guard(app_env="production", allow_value="true", confirmed=True)
    with pytest.raises(RuntimeError, match="not_allowed"):
        validate_execution_guard(app_env="acceptance", allow_value=None, confirmed=True)
    with pytest.raises(RuntimeError, match="confirmation_required"):
        validate_execution_guard(app_env="acceptance", allow_value="true", confirmed=False)


def test_acceptance_bootstrap_password_sources_are_protected(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="password_source_required"):
        read_bootstrap_password({})
    with pytest.raises(RuntimeError, match="too_short"):
        read_bootstrap_password({PASSWORD_ENV: "short"})
    with pytest.raises(RuntimeError, match="password_source_required"):
        read_bootstrap_password({PASSWORD_ENV: PASSWORD, PASSWORD_FILE_ENV: "ignored"})

    password_file = tmp_path / "acceptance-password"
    password_file.write_text(PASSWORD, encoding="utf-8")
    password_file.chmod(0o644)
    with pytest.raises(RuntimeError, match="permissions_must_be_0600"):
        read_bootstrap_password({PASSWORD_FILE_ENV: os.fspath(password_file)})
    password_file.chmod(0o600)
    assert read_bootstrap_password({PASSWORD_FILE_ENV: os.fspath(password_file)}) == PASSWORD
    assert len(PASSWORD) >= MINIMUM_PASSWORD_LENGTH


@pytest.mark.asyncio
async def test_acceptance_bootstrap_is_idempotent_and_auth_tenant_volunteer_compatible(
    isolated_application_database_pool: None,
) -> None:
    # Access grants are intentionally time-bounded. Use the current clock so this
    # acceptance fixture does not become invalid merely because the calendar moved.
    clock = datetime.now(timezone.utc)
    async with session_factory() as session:
        first = await bootstrap_acceptance(session, password=PASSWORD, now=clock)
        second = await bootstrap_acceptance(session, password=PASSWORD, now=clock)

        assert {fixture.status for fixture in first.__dict__.values()} == {"created"}, {
            key: fixture.status for key, fixture in first.__dict__.items()
        }
        assert {fixture.status for fixture in second.__dict__.values()} == {"reused"}
        assert first.tenant_a.id == second.tenant_a.id
        assert first.volunteer_a.id == second.volunteer_a.id
        assert first.grant_a.id == second.grant_a.id
        assert first.animal_b.id == second.animal_b.id

        await set_platform_scope(session)
        assert (
            await session.scalar(
                select(func.count(Organization.id)).where(
                    Organization.code.in_([TENANT_A_CODE, TENANT_B_CODE])
                )
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count(User.id)).where(
                    User.username.in_([ADMIN_A_USERNAME, VOLUNTEER_A_USERNAME])
                )
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count(OrganizationMembership.id)).where(
                    OrganizationMembership.organization_id.in_(
                        [first.tenant_a.id, first.tenant_b.id]
                    )
                )
            )
            == 3
        )
        assert (
            await session.scalar(
                select(func.count(VolunteerAccessGrant.id)).where(
                    VolunteerAccessGrant.organization_id == first.tenant_a.id
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(Animal.id)).where(
                    Animal.organization_id.in_([first.tenant_a.id, first.tenant_b.id])
                )
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count(AnimalQrCode.id)).where(
                    AnimalQrCode.organization_id.in_([first.tenant_a.id, first.tenant_b.id])
                )
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count(DailyReportableScope.id)).where(
                    DailyReportableScope.organization_id == first.tenant_a.id
                )
            )
            == 1
        )

        auth_repository = AuthenticationRepository(session)
        login = await SessionService(
            auth_repository,
            password_hasher=Argon2PasswordHasher(),
            access_token=_token_adapter(),
        ).login(username=VOLUNTEER_A_USERNAME, password=PASSWORD)
        assert login["access_token"]
        assert {item["id"] for item in login["organizations"]} == {first.tenant_a.id}

        await auth_repository.set_authentication_context_scope(
            first.volunteer_a.id, first.tenant_b.id
        )
        assert (
            await auth_repository.get_effective_membership(first.volunteer_a.id, first.tenant_b.id)
            is None
        )

        await set_organization_scope(session, first.tenant_a.id)
        qr_a = await QrCodeRepository(session, first.tenant_a.id).get(first.qr_a.id)
        assert qr_a is not None
        from services.api.app.application.qr_token_service import printable_token_for

        raw_qr_a = printable_token_for(qr_a)
        assert raw_qr_a
        candidate = await AnimalSelectionService(
            AnimalRepository(session, first.tenant_a.id),
            QrCodeRepository(session, first.tenant_a.id),
            VolunteerReportingAuthorizationService(
                AuthenticationRepository(session), AnimalRepository(session, first.tenant_a.id)
            ),
        ).resolve_qr(
            raw_token=raw_qr_a,
            user_id=first.volunteer_a.id,
            organization_id=first.tenant_a.id,
            membership_id=first.volunteer_membership_a.id,
            role="VOLUNTEER",
        )
        assert candidate.animal.id == first.animal_a.id

        confirmation = issue_animal_confirmation_token(
            user_id=first.volunteer_a.id,
            organization_id=first.tenant_a.id,
            membership_id=first.volunteer_membership_a.id,
            session_id=login["session_id"],
            animal_id=first.animal_a.id,
        )
        drafts = CareReportDraftRepository(session, first.tenant_a.id)
        draft, _ = await CreateReportDraftService(drafts).create(
            volunteer_user_id=first.volunteer_a.id,
            organization_id=first.tenant_a.id,
            membership_id=first.volunteer_membership_a.id,
            session_id=login["session_id"],
            animal_id=first.animal_a.id,
            confirmation_token=confirmation,
        )
        answers = {
            "walk_completion": "walk_completion.not_done",
            "activity": "activity.not_observed",
            "gait": "gait.not_observed",
            "defecation": "defecation.not_observed",
            "animal_interaction": "animal_interaction.uncertain",
            "appearance_special_status": "appearance.not_observed",
        }
        assert set(answers) == set(REQUIRED_ANSWER_KEYS)
        draft.answers = answers
        draft.current_step = "reviewing"
        animal_a = await AnimalRepository(session, first.tenant_a.id).get(first.animal_a.id)
        assert animal_a is not None
        report = await ReportSubmissionService(
            drafts,
            CareReportRepository(session, first.tenant_a.id),
            scope_validator=lambda animal_id: ReportableScopeRepository(
                session, first.tenant_a.id
            ).is_animal_reportable(
                animal_id=animal_id,
                volunteer_user_id=first.volunteer_a.id,
                now=clock,
            ),
        ).submit(
            draft_id=draft.id,
            volunteer_user_id=first.volunteer_a.id,
            animal=animal_a,
            idempotency_key="acceptance-bootstrap-test-report",
            note="Synthetic acceptance test only",
        )
        assert report.organization_id == first.tenant_a.id

        await set_organization_scope(session, first.tenant_b.id)
        qr_b = await QrCodeRepository(session, first.tenant_b.id).get(first.qr_b.id)
        animal_b = await AnimalRepository(session, first.tenant_b.id).get(first.animal_b.id)
        assert qr_b is not None and animal_b is not None
        assert animal_b.shelter_number == ANIMAL_B_NUMBER
        from services.api.app.application.qr_token_service import printable_token_for

        raw_qr_b = printable_token_for(qr_b)
        assert raw_qr_b
        with pytest.raises(DomainError, match="目前無法開始此照護回報"):
            await AnimalSelectionService(
                AnimalRepository(session, first.tenant_b.id),
                QrCodeRepository(session, first.tenant_b.id),
                VolunteerReportingAuthorizationService(
                    AuthenticationRepository(session),
                    AnimalRepository(session, first.tenant_b.id),
                ),
            ).resolve_qr(
                raw_token=raw_qr_b,
                user_id=first.volunteer_a.id,
                organization_id=first.tenant_b.id,
                membership_id=first.volunteer_membership_a.id,
                role="VOLUNTEER",
            )

        await session.rollback()
