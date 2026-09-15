"""Guarded operator bootstrap for deterministic synthetic acceptance identities."""

from __future__ import annotations

import argparse
import asyncio
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

ALLOWED_ENVIRONMENTS = frozenset({"acceptance", "demo", "gcp-demo", "local"})
CONFIRMATION_ENV = "STRAYHUB_ALLOW_ACCEPTANCE_BOOTSTRAP"
PASSWORD_ENV = "ACCEPTANCE_BOOTSTRAP_PASSWORD"
PASSWORD_FILE_ENV = "ACCEPTANCE_BOOTSTRAP_PASSWORD_FILE"
MINIMUM_PASSWORD_LENGTH = 20

TENANT_A_CODE = "STRAYHUB-ACCEPTANCE-A"
TENANT_B_CODE = "STRAYHUB-ACCEPTANCE-B"
TENANT_A_SERVICE_AREA = "臺北市"
TENANT_B_SERVICE_AREA = "新北市"
ADMIN_A_USERNAME = "acceptance-admin-a@strayhub.local"
ADMIN_B_USERNAME = "acceptance-admin-b@strayhub.local"
VOLUNTEER_A_USERNAME = "acceptance-volunteer-a@strayhub.local"
ANIMAL_A_NUMBER = "ACCEPTANCE-A-ANIMAL"
ANIMAL_B_NUMBER = "ACCEPTANCE-B-ANIMAL"
SYNTHETIC_LINE_SUBJECT = "Uacceptancevolunteer0000000000000001"

FixtureStatus = Literal["created", "reused", "updated", "would_create", "would_update"]


def stable_id(label: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"strayhub:acceptance-bootstrap:{label}")


@dataclass(frozen=True)
class FixtureResult:
    status: FixtureStatus
    id: UUID


@dataclass(frozen=True)
class AcceptanceBootstrapResult:
    tenant_a: FixtureResult
    admin_a: FixtureResult
    admin_membership_a: FixtureResult
    volunteer_a: FixtureResult
    volunteer_membership_a: FixtureResult
    grant_a: FixtureResult
    animal_a: FixtureResult
    qr_a: FixtureResult
    reportable_scope_a: FixtureResult
    tenant_b: FixtureResult
    admin_b: FixtureResult
    admin_membership_b: FixtureResult
    animal_b: FixtureResult
    qr_b: FixtureResult


def validate_execution_guard(
    *, app_env: str | None, allow_value: str | None, confirmed: bool
) -> str:
    environment = (app_env or "").strip().lower()
    if environment not in ALLOWED_ENVIRONMENTS:
        allowed = ", ".join(sorted(ALLOWED_ENVIRONMENTS))
        raise RuntimeError(f"acceptance_bootstrap_environment_denied: expected one of {allowed}")
    if (allow_value or "").strip().lower() != "true":
        raise RuntimeError(f"acceptance_bootstrap_not_allowed: set {CONFIRMATION_ENV}=true")
    if not confirmed:
        raise RuntimeError("acceptance_bootstrap_confirmation_required")
    return environment


def _password_from_file(raw_path: str) -> str:
    path = Path(raw_path)
    file_stat = path.stat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise RuntimeError("acceptance_bootstrap_password_file_not_regular")
    if stat.S_IMODE(file_stat.st_mode) & 0o077:
        raise RuntimeError("acceptance_bootstrap_password_file_permissions_must_be_0600")
    return path.read_text(encoding="utf-8").rstrip("\r\n")


def read_bootstrap_password(environ: dict[str, str] | os._Environ[str]) -> str:
    inline = environ.get(PASSWORD_ENV, "")
    file_path = environ.get(PASSWORD_FILE_ENV, "")
    if bool(inline) == bool(file_path):
        raise RuntimeError(
            f"acceptance_bootstrap_password_source_required: set exactly one of "
            f"{PASSWORD_ENV} or {PASSWORD_FILE_ENV}"
        )
    password = inline if inline else _password_from_file(file_path)
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise RuntimeError(
            f"acceptance_bootstrap_password_too_short: minimum {MINIMUM_PASSWORD_LENGTH} characters"
        )
    return password


async def _ensure_organization(
    session: AsyncSession, *, code: str, name: str, service_area: str
) -> tuple[Any, FixtureStatus]:
    from services.api.app.application.audit_service import AuditService
    from services.api.app.application.organization_management import OrganizationManagementService
    from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
    from services.api.app.persistence.models.identity import Organization
    from services.api.app.persistence.repositories.organization_repository import (
        OrganizationRepository,
    )
    from sqlalchemy import select

    organization = await session.scalar(select(Organization).where(Organization.code == code))
    if organization is None:
        organization = await OrganizationManagementService(
            OrganizationRepository(session), Argon2PasswordHasher()
        ).create(code=code, name=name)
        organization.name = name
        organization.status = "active"
        organization.address = "Synthetic acceptance data only"
        organization.service_area = service_area
        await AuditService(session).record(
            organization_id=None,
            actor_user_id=None,
            actor_reference="acceptance-bootstrap",
            action="organization.created",
            resource_type="organization",
            resource_id=organization.id,
            source_channel="operator_cli",
            after={"code": code, "name": name, "synthetic": True},
        )
        return organization, "created"
    if organization.name != name:
        raise RuntimeError(f"acceptance_fixture_collision: organization code {code}")
    if organization.service_area not in {service_area, "Acceptance"}:
        raise RuntimeError(f"acceptance_fixture_collision: organization service area {code}")
    changed = False
    if organization.status != "active":
        organization.status = "active"
        changed = True
    if organization.service_area == "Acceptance":
        organization.service_area = service_area
        changed = True
    return organization, "updated" if changed else "reused"


async def _ensure_admin(
    session: AsyncSession,
    *,
    organization: Any,
    username: str,
    display_name: str,
    password: str,
) -> tuple[Any, Any, FixtureStatus, FixtureStatus]:
    from services.api.app.application.audit_service import AuditService
    from services.api.app.application.organization_management import OrganizationManagementService
    from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
    from services.api.app.persistence.database.scope import set_organization_scope
    from services.api.app.persistence.repositories.organization_repository import (
        OrganizationRepository,
    )

    repository = OrganizationRepository(session)
    service = OrganizationManagementService(repository, Argon2PasswordHasher())
    hasher = Argon2PasswordHasher()
    user = await repository.user_by_username(username)
    user_status: FixtureStatus = "reused"
    if user is None:
        user = await service.create_initial_admin(
            organization_id=organization.id,
            username=username,
            temporary_password=password,
        )
        user.display_name = display_name
        user_status = "created"
    else:
        if user.platform_role is not None or user.status not in {"active", "disabled"}:
            raise RuntimeError(f"acceptance_fixture_collision: user {username}")
        changed = False
        if user.display_name != display_name:
            user.display_name = display_name
            changed = True
        if user.status != "active":
            user.status = "active"
            changed = True
        if not user.password_hash or not hasher.verify(password, user.password_hash):
            user.password_hash = hasher.hash(password)
            changed = True
        user_status = "updated" if changed else "reused"

    membership = await repository.membership(user.id, organization.id)
    membership_status: FixtureStatus = "created" if user_status == "created" else "reused"
    if membership is None:
        membership = await service.create_membership(
            organization_id=organization.id,
            user_id=user.id,
            role="SHELTER_ADMIN",
        )
        membership_status = "created"
    elif membership.role != "SHELTER_ADMIN":
        raise RuntimeError(f"acceptance_fixture_collision: admin membership {username}")
    elif membership.status != "active":
        membership.status = "active"
        membership_status = "updated"

    await set_organization_scope(session, organization.id)
    if user_status == "created":
        await AuditService(session).record(
            organization_id=organization.id,
            actor_user_id=None,
            actor_reference="acceptance-bootstrap",
            action="user.created",
            resource_type="user",
            resource_id=user.id,
            source_channel="operator_cli",
            after={"username": username, "display_name": display_name, "synthetic": True},
        )
    if membership_status == "created":
        await AuditService(session).record(
            organization_id=organization.id,
            actor_user_id=None,
            actor_reference="acceptance-bootstrap",
            action="membership.created",
            resource_type="organization_membership",
            resource_id=membership.id,
            source_channel="operator_cli",
            after={"user_id": user.id, "role": membership.role, "synthetic": True},
        )
    return user, membership, user_status, membership_status


class _VerifierMustNotRun:
    async def verify(self, _token: str) -> str:
        raise RuntimeError("acceptance bootstrap must pass its synthetic server-side identity")


async def _ensure_volunteer(
    session: AsyncSession,
    *,
    organization: Any,
    admin_user: Any,
    password: str,
    now: datetime,
) -> tuple[Any, Any, Any, FixtureStatus, FixtureStatus, FixtureStatus]:
    from services.api.app.application.audit_service import AuditService
    from services.api.app.application.volunteer_access_service import VolunteerAccessService
    from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
    from services.api.app.persistence.database.scope import (
        set_organization_scope,
        set_platform_scope,
    )
    from services.api.app.persistence.models.identity import LineUserBinding
    from services.api.app.persistence.repositories.authentication_repository import (
        AuthenticationRepository,
    )
    from services.api.app.persistence.repositories.volunteer_access_repository import (
        VolunteerAccessRepository,
    )

    await set_platform_scope(session)
    identities = AuthenticationRepository(session)
    user = await identities.find_user_by_username(VOLUNTEER_A_USERNAME)
    user_status: FixtureStatus = "reused"

    await set_organization_scope(session, organization.id)
    repository = VolunteerAccessRepository(session, organization.id)
    service = await VolunteerAccessService.for_organization(
        organization.id,
        repository,
        identities,
        _VerifierMustNotRun(),
        audit=AuditService(session),
    )
    binding = await identities.get_line_binding(SYNTHETIC_LINE_SUBJECT)
    if user is None:
        submitted = await service.submit(
            id_token="",
            verified_line_user_id=SYNTHETIC_LINE_SUBJECT,
            entry_reference_id=None,
            organization_id=organization.id,
            client_request_id=stable_id("volunteer-a-application"),
            consent_acknowledged=True,
            now=now,
        )
        user = await identities.get_user(submitted.status.application.user_id)
        if user is None:
            raise RuntimeError("acceptance_bootstrap_volunteer_creation_failed")
        binding = await identities.get_line_binding(SYNTHETIC_LINE_SUBJECT)
        user.username = VOLUNTEER_A_USERNAME
        user.display_name = "Acceptance Volunteer A"
        user.password_hash = Argon2PasswordHasher().hash(password)
        user_status = "created"
    else:
        if user.platform_role is not None:
            raise RuntimeError("acceptance_fixture_collision: volunteer has platform role")
        if binding is None:
            binding = await identities.add(
                LineUserBinding(
                    line_user_id=SYNTHETIC_LINE_SUBJECT,
                    user_id=user.id,
                    status="active",
                )
            )
            user_status = "updated"
        elif binding.user_id != user.id:
            raise RuntimeError("acceptance_fixture_collision: synthetic LINE binding")
        hasher = Argon2PasswordHasher()
        changed = False
        if user.display_name != "Acceptance Volunteer A":
            user.display_name = "Acceptance Volunteer A"
            changed = True
        if user.status != "active":
            user.status = "active"
            changed = True
        if not user.password_hash or not hasher.verify(password, user.password_hash):
            user.password_hash = hasher.hash(password)
            changed = True
        if changed:
            user_status = "updated"

    applications = await repository.applications_for_user(user.id)
    application = applications[0] if applications else None
    if application is None or application.status in {"rejected", "withdrawn"}:
        submitted = await service.submit(
            id_token="",
            verified_line_user_id=SYNTHETIC_LINE_SUBJECT,
            entry_reference_id=None,
            organization_id=organization.id,
            client_request_id=stable_id(f"volunteer-a-application-{len(applications)}"),
            consent_acknowledged=True,
            now=now,
        )
        application = submitted.status.application
    if application is None:
        raise RuntimeError("acceptance_bootstrap_application_missing")

    grant = await repository.grant_for_application(application.id)
    membership = await identities.get_membership(user.id, organization.id)
    membership_status: FixtureStatus = "reused"
    grant_status: FixtureStatus = "reused"
    minimum_expiry = now + timedelta(days=1)
    if application.status == "pending":
        application, membership, grant = await service.decide_application(
            application_id=application.id,
            expected_version=application.version,
            decision="approve",
            actor_user_id=admin_user.id,
            reason="Synthetic E5 acceptance fixture",
            valid_from=now - timedelta(hours=1),
            expires_at=now + timedelta(days=7),
            now=now,
        )
        membership_status = "created"
        grant_status = "created"
    elif grant is None or membership is None:
        raise RuntimeError("acceptance_fixture_malformed: approved volunteer projection missing")
    elif (
        grant.organization_id != organization.id
        or membership.organization_id != organization.id
        or grant.membership_id != membership.id
        or membership.role != "VOLUNTEER"
    ):
        raise RuntimeError("acceptance_fixture_collision: volunteer grant scope")
    elif grant.status == "active" and grant.expires_at <= minimum_expiry:
        grant = await service.mutate_grant(
            grant_id=grant.id,
            expected_version=grant.version,
            action="update_period",
            actor_user_id=admin_user.id,
            valid_from=now - timedelta(hours=1),
            expires_at=now + timedelta(days=7),
            reason="Refresh synthetic E5 acceptance window",
            now=now,
        )
        membership_status = "updated"
        grant_status = "updated"
    elif grant.status != "active" or membership.status != "active":
        raise RuntimeError("acceptance_fixture_malformed: volunteer access is terminal")

    assert membership is not None and grant is not None and binding is not None
    return user, membership, grant, user_status, membership_status, grant_status


async def _ensure_animal(
    session: AsyncSession,
    *,
    organization: Any,
    shelter_number: str,
    name: str,
) -> tuple[Any, FixtureStatus]:
    from services.api.app.application.audit_service import AuditService
    from services.api.app.persistence.models.animal import Animal
    from services.api.app.persistence.repositories.animal_repository import AnimalRepository
    from sqlalchemy import select

    repository = AnimalRepository(session, organization.id)
    animal = await session.scalar(
        select(Animal).where(
            Animal.organization_id == organization.id,
            Animal.shelter_number == shelter_number,
        )
    )
    if animal is None:
        animal = await repository.add(
            Animal(
                organization_id=organization.id,
                name=name,
                shelter_number=shelter_number,
                status="active",
                sex="unknown",
                care_guidance="Synthetic acceptance fixture only",
            )
        )
        await AuditService(session).record(
            organization_id=organization.id,
            actor_user_id=None,
            actor_reference="acceptance-bootstrap",
            action="animal.created",
            resource_type="animal",
            resource_id=animal.id,
            source_channel="operator_cli",
            after={"shelter_number": shelter_number, "name": name, "synthetic": True},
        )
        return animal, "created"
    if animal.name != name:
        raise RuntimeError(f"acceptance_fixture_collision: animal {shelter_number}")
    if animal.status != "active":
        animal.status = "active"
        return animal, "updated"
    return animal, "reused"


async def _ensure_qr(
    session: AsyncSession, *, organization_id: UUID, animal_id: UUID
) -> tuple[Any, FixtureStatus]:
    from services.api.app.application.qr_token_service import QrTokenService
    from services.api.app.persistence.repositories.animal_repository import AnimalRepository
    from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository

    qr, _raw_token, created = await QrTokenService(
        AnimalRepository(session, organization_id),
        QrCodeRepository(session, organization_id),
    ).create_or_reuse(animal_id=animal_id)
    return qr, "created" if created else "reused"


async def _ensure_reportable_scope(
    session: AsyncSession,
    *,
    organization_id: UUID,
    animal_id: UUID,
    volunteer_user_id: UUID,
    admin_user_id: UUID,
    now: datetime,
) -> tuple[Any, FixtureStatus]:
    from services.api.app.application.audit_service import AuditService
    from services.api.app.application.reportable_scope_service import ReportableScopeService
    from services.api.app.persistence.models.reportable_scope import DailyReportableScope
    from sqlalchemy import select

    scope = await session.scalar(
        select(DailyReportableScope).where(
            DailyReportableScope.organization_id == organization_id,
            DailyReportableScope.animal_id == animal_id,
            DailyReportableScope.volunteer_user_id == volunteer_user_id,
        )
    )
    starts_at = now - timedelta(hours=1)
    ends_at = now + timedelta(days=7)
    await ReportableScopeService(session).validate_target(
        organization_id=organization_id,
        animal_id=animal_id,
        area_id=None,
        volunteer_user_id=volunteer_user_id,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    if scope is None:
        scope = DailyReportableScope(
            id=stable_id("reportable-scope-a"),
            organization_id=organization_id,
            animal_id=animal_id,
            volunteer_user_id=volunteer_user_id,
            starts_at=starts_at,
            ends_at=ends_at,
            status="active",
        )
        session.add(scope)
        await session.flush()
        await AuditService(session).record(
            organization_id=organization_id,
            actor_user_id=admin_user_id,
            action="reportable_scope.created",
            resource_type="DailyReportableScope",
            resource_id=scope.id,
            source_channel="operator_cli",
            after={
                "animal_id": animal_id,
                "volunteer_user_id": volunteer_user_id,
                "synthetic": True,
            },
        )
        return scope, "created"
    if scope.status != "active" or scope.ends_at <= now + timedelta(days=1):
        scope.status = "active"
        scope.starts_at = starts_at
        scope.ends_at = ends_at
        return scope, "updated"
    return scope, "reused"


async def _cancel_interrupted_acceptance_drafts(
    session: AsyncSession, *, organization_id: UUID, volunteer_user_id: UUID
) -> int:
    """Reset only unfinished synthetic acceptance work so rehearsals are repeatable."""
    from services.api.app.persistence.models.care_report_draft import CareReportDraft
    from sqlalchemy import select

    drafts = list(
        (
            await session.scalars(
                select(CareReportDraft).where(
                    CareReportDraft.organization_id == organization_id,
                    CareReportDraft.volunteer_user_id == volunteer_user_id,
                    CareReportDraft.status == "active",
                )
            )
        ).all()
    )
    for draft in drafts:
        draft.status = "cancelled"
        draft.current_step = "cancelled"
    await session.flush()
    return len(drafts)


async def bootstrap_acceptance(
    session: AsyncSession,
    *,
    password: str,
    now: datetime | None = None,
) -> AcceptanceBootstrapResult:
    from scripts.seed_observation_vocabulary import seed_vocabulary
    from services.api.app.persistence.database.scope import (
        set_organization_scope,
        set_platform_scope,
    )

    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise RuntimeError("acceptance_bootstrap_password_too_short")
    clock = now or datetime.now(timezone.utc)
    await set_platform_scope(session)
    await seed_vocabulary(session)

    tenant_a, tenant_a_status = await _ensure_organization(
        session,
        code=TENANT_A_CODE,
        name="Acceptance Shelter A",
        service_area=TENANT_A_SERVICE_AREA,
    )
    await set_platform_scope(session)
    tenant_b, tenant_b_status = await _ensure_organization(
        session,
        code=TENANT_B_CODE,
        name="Acceptance Shelter B",
        service_area=TENANT_B_SERVICE_AREA,
    )

    await set_platform_scope(session)
    admin_a, admin_membership_a, admin_a_status, admin_membership_a_status = await _ensure_admin(
        session,
        organization=tenant_a,
        username=ADMIN_A_USERNAME,
        display_name="Acceptance Admin A",
        password=password,
    )
    await set_platform_scope(session)
    admin_b, admin_membership_b, admin_b_status, admin_membership_b_status = await _ensure_admin(
        session,
        organization=tenant_b,
        username=ADMIN_B_USERNAME,
        display_name="Acceptance Admin B",
        password=password,
    )

    (
        volunteer_a,
        volunteer_membership_a,
        grant_a,
        volunteer_status,
        membership_status,
        grant_status,
    ) = await _ensure_volunteer(
        session,
        organization=tenant_a,
        admin_user=admin_a,
        password=password,
        now=clock,
    )

    await set_organization_scope(session, tenant_a.id)
    animal_a, animal_a_status = await _ensure_animal(
        session,
        organization=tenant_a,
        shelter_number=ANIMAL_A_NUMBER,
        name="Acceptance Animal A",
    )
    qr_a, qr_a_status = await _ensure_qr(
        session, organization_id=tenant_a.id, animal_id=animal_a.id
    )
    scope_a, scope_a_status = await _ensure_reportable_scope(
        session,
        organization_id=tenant_a.id,
        animal_id=animal_a.id,
        volunteer_user_id=volunteer_a.id,
        admin_user_id=admin_a.id,
        now=clock,
    )
    await _cancel_interrupted_acceptance_drafts(
        session,
        organization_id=tenant_a.id,
        volunteer_user_id=volunteer_a.id,
    )

    await set_organization_scope(session, tenant_b.id)
    animal_b, animal_b_status = await _ensure_animal(
        session,
        organization=tenant_b,
        shelter_number=ANIMAL_B_NUMBER,
        name="Acceptance Animal B",
    )
    qr_b, qr_b_status = await _ensure_qr(
        session, organization_id=tenant_b.id, animal_id=animal_b.id
    )

    return AcceptanceBootstrapResult(
        tenant_a=FixtureResult(tenant_a_status, tenant_a.id),
        admin_a=FixtureResult(admin_a_status, admin_a.id),
        admin_membership_a=FixtureResult(admin_membership_a_status, admin_membership_a.id),
        volunteer_a=FixtureResult(volunteer_status, volunteer_a.id),
        volunteer_membership_a=FixtureResult(membership_status, volunteer_membership_a.id),
        grant_a=FixtureResult(grant_status, grant_a.id),
        animal_a=FixtureResult(animal_a_status, animal_a.id),
        qr_a=FixtureResult(qr_a_status, qr_a.id),
        reportable_scope_a=FixtureResult(scope_a_status, scope_a.id),
        tenant_b=FixtureResult(tenant_b_status, tenant_b.id),
        admin_b=FixtureResult(admin_b_status, admin_b.id),
        admin_membership_b=FixtureResult(admin_membership_b_status, admin_membership_b.id),
        animal_b=FixtureResult(animal_b_status, animal_b.id),
        qr_b=FixtureResult(qr_b_status, qr_b.id),
    )


def _safe_summary(result: AcceptanceBootstrapResult, *, dry_run: bool) -> str:
    def line(label: str, fixture: FixtureResult) -> str:
        dry_run_status: dict[FixtureStatus, FixtureStatus] = {
            "created": "would_create",
            "updated": "would_update",
        }
        status = dry_run_status.get(fixture.status, fixture.status) if dry_run else fixture.status
        return f"  {label}: {fixture.id} ({status})"

    return "\n".join(
        [
            "Acceptance bootstrap complete"
            if not dry_run
            else "Acceptance bootstrap dry run complete",
            "Tenant A:",
            line("organization", result.tenant_a),
            line("admin", result.admin_a),
            line("admin membership", result.admin_membership_a),
            line("volunteer", result.volunteer_a),
            line("volunteer membership", result.volunteer_membership_a),
            line("grant", result.grant_a),
            line("animal", result.animal_a),
            line("qr", result.qr_a),
            line("reportable scope", result.reportable_scope_a),
            "Tenant B:",
            line("organization", result.tenant_b),
            line("admin", result.admin_b),
            line("admin membership", result.admin_membership_b),
            line("animal", result.animal_b),
            line("qr", result.qr_b),
        ]
    )


async def _run(args: argparse.Namespace) -> int:
    validate_execution_guard(
        app_env=os.getenv("APP_ENV"),
        allow_value=os.getenv(CONFIRMATION_ENV),
        confirmed=args.confirm_synthetic_data,
    )
    password = read_bootstrap_password(os.environ)

    # Create the one-shot operator session only after every guard passes. The
    # migration process contract validates a non-local URL without requiring
    # API-only JWT or object-storage configuration.
    from services.api.app.config.settings import Settings
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    settings = Settings().validate_runtime_safety(process="migration")
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            try:
                result = await bootstrap_acceptance(session, password=password)
                if args.dry_run:
                    await session.rollback()
                else:
                    await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()
    print(_safe_summary(result, dry_run=args.dry_run))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-synthetic-data",
        action="store_true",
        help="confirm creation or repair of unmistakably synthetic acceptance fixtures",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and report planned fixture actions, then roll back",
    )
    raise SystemExit(asyncio.run(_run(parser.parse_args())))


if __name__ == "__main__":
    main()
