"""Legacy test-fixture implementation; prefer scripts.seed_test_fixtures.

Never invoke this fixture universe from normal demo bootstrap.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid5

from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.identity import (
    LineUserBinding,
    Organization,
    OrganizationMembership,
    SessionRecord,
    User,
    WebhookSession,
)
from services.api.app.persistence.models.qr_code import AnimalQrCode
from services.api.app.persistence.models.reportable_scope import DailyReportableScope
from services.api.app.persistence.models.shelter_area import ShelterArea
from services.api.app.persistence.models.volunteer_access import (
    OrganizationVolunteerAccessPolicy,
    ShelterVolunteerEntryReference,
    VolunteerAccessGrant,
    VolunteerApplication,
    VolunteerNotificationDelivery,
)
from sqlalchemy import select

from .seed_observation_vocabulary import seed_vocabulary

VOLUNTEER_FIXTURE_NAMESPACE = UUID("41c08fbb-fef2-4930-abd9-bd1f77226888")


def _fixture_uuid(label: str):
    return uuid5(VOLUNTEER_FIXTURE_NAMESPACE, label)


async def _seed_pending_applicant_set(
    session,
    *,
    organization: Organization,
    prefix: str,
    count: int,
    now: datetime,
) -> None:
    sentinel = f"local-applicant-{prefix}-{count:04d}"
    if (
        await session.execute(select(User.id).where(User.username == sentinel))
    ).scalar_one_or_none() is not None:
        return
    users = []
    bindings = []
    applications = []
    for index in range(1, count + 1):
        key = f"{prefix}-{index:04d}"
        user_id = _fixture_uuid(f"user:{organization.code}:{key}")
        users.append(
            User(
                id=user_id,
                username=f"local-applicant-{key}",
                display_name=f"批次志工 {key}",
                status="active",
            )
        )
        bindings.append(
            LineUserBinding(
                id=_fixture_uuid(f"binding:{organization.code}:{key}"),
                line_user_id=f"Ulocal-applicant-{organization.code.lower()}-{key}",
                user_id=user_id,
                status="active",
            )
        )
        applications.append(
            VolunteerApplication(
                id=_fixture_uuid(f"application:{organization.code}:{key}"),
                organization_id=organization.id,
                user_id=user_id,
                status="pending",
                source_channel="liff",
                client_request_id=_fixture_uuid(f"client-request:{organization.code}:{key}"),
                submitted_at=now - timedelta(minutes=index),
            )
        )
    session.add_all(users)
    await session.flush()
    session.add_all([*bindings, *applications])
    await session.flush()


async def _seed_failed_notifications(
    session,
    *,
    organization: Organization,
    volunteer: User,
    line_binding: LineUserBinding,
    now: datetime,
) -> None:
    for event_type in (
        "application_submitted",
        "application_withdrawn",
        "application_approved",
        "application_rejected",
        "grant_period_updated",
        "grant_expired",
        "grant_revoked",
    ):
        key = f"local:{organization.code}:{event_type}:v1"
        await _get_or_create(
            session,
            VolunteerNotificationDelivery,
            select(VolunteerNotificationDelivery).where(
                VolunteerNotificationDelivery.organization_id == organization.id,
                VolunteerNotificationDelivery.idempotency_key == key,
            ),
            lambda event_type=event_type, key=key: VolunteerNotificationDelivery(
                organization_id=organization.id,
                user_id=volunteer.id,
                line_binding_id=line_binding.id,
                event_type=event_type,
                resource_type="volunteer_access",
                resource_id=_fixture_uuid(
                    f"notification-resource:{organization.code}:{event_type}"
                ),
                idempotency_key=key,
                payload={"organization_name": organization.name},
                status="failed",
                attempt_count=3,
                last_error_code="local_line_delivery_failed",
                last_failed_at=now,
            ),
        )


async def _seed_application_and_grant_state(
    session,
    *,
    organization: Organization,
    approver: User,
    policy: OrganizationVolunteerAccessPolicy,
    state: str,
    now: datetime,
) -> User:
    username = f"local-volunteer-state-{state.lower()}"
    user = await _get_or_create(
        session,
        User,
        select(User).where(User.username == username),
        lambda: User(username=username, display_name=f"志工狀態 {state}", status="active"),
    )
    await _get_or_create(
        session,
        LineUserBinding,
        select(LineUserBinding).where(LineUserBinding.user_id == user.id),
        lambda: LineUserBinding(
            line_user_id=f"Ulocal-volunteer-state-{state.lower()}",
            user_id=user.id,
            status="active",
        ),
    )
    if state == "rejected":
        await _get_or_create(
            session,
            VolunteerApplication,
            select(VolunteerApplication).where(
                VolunteerApplication.organization_id == organization.id,
                VolunteerApplication.user_id == user.id,
                VolunteerApplication.status == "rejected",
            ),
            lambda: VolunteerApplication(
                organization_id=organization.id,
                user_id=user.id,
                status="rejected",
                source_channel="liff",
                submitted_at=now - timedelta(days=2),
                decided_at=now - timedelta(days=1),
                decided_by_user_id=approver.id,
                decision_reason="本機拒絕狀態 fixture",
            ),
        )
        return user

    if state == "future":
        valid_from, expires_at, membership_status, grant_status = (
            now + timedelta(days=1),
            now + timedelta(days=8),
            "active",
            "active",
        )
    elif state == "expired":
        valid_from, expires_at, membership_status, grant_status = (
            now - timedelta(days=8),
            now - timedelta(days=1),
            "expired",
            "expired",
        )
    elif state == "revoked":
        valid_from, expires_at, membership_status, grant_status = (
            now - timedelta(days=1),
            now + timedelta(days=6),
            "revoked",
            "revoked",
        )
    elif state == "disabled_user":
        valid_from, expires_at, membership_status, grant_status = (
            now - timedelta(days=1),
            now + timedelta(days=6),
            "active",
            "active",
        )
    else:
        raise ValueError(f"unsupported fixture state: {state}")

    membership = await _get_or_create(
        session,
        OrganizationMembership,
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == user.id,
        ),
        lambda: OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role="VOLUNTEER",
            status=membership_status,
            valid_from=valid_from,
            expires_at=expires_at,
            access_version=1,
        ),
    )
    application = await _get_or_create(
        session,
        VolunteerApplication,
        select(VolunteerApplication).where(
            VolunteerApplication.organization_id == organization.id,
            VolunteerApplication.user_id == user.id,
            VolunteerApplication.status == "approved",
        ),
        lambda: VolunteerApplication(
            organization_id=organization.id,
            user_id=user.id,
            status="approved",
            source_channel="management",
            submitted_at=now - timedelta(days=2),
            decided_at=now - timedelta(days=1),
            decided_by_user_id=approver.id,
        ),
    )
    await _get_or_create(
        session,
        VolunteerAccessGrant,
        select(VolunteerAccessGrant).where(VolunteerAccessGrant.application_id == application.id),
        lambda: VolunteerAccessGrant(
            organization_id=organization.id,
            user_id=user.id,
            membership_id=membership.id,
            application_id=application.id,
            status=grant_status,
            valid_from=valid_from,
            expires_at=expires_at,
            approved_at=now - timedelta(days=1),
            approved_by_user_id=approver.id,
            policy_version_used=policy.version,
            duration_hours_used=policy.default_grant_duration_hours,
            revoked_at=now if state == "revoked" else None,
            revoked_by_user_id=approver.id if state == "revoked" else None,
            revocation_reason="本機撤銷狀態 fixture" if state == "revoked" else None,
        ),
    )
    if state == "disabled_user":
        user.status = "disabled"
        await _get_or_create(
            session,
            SessionRecord,
            select(SessionRecord).where(
                SessionRecord.user_id == user.id,
                SessionRecord.active_organization_id == organization.id,
            ),
            lambda: SessionRecord(
                user_id=user.id,
                active_organization_id=organization.id,
                status="active",
                expires_at=now + timedelta(days=1),
            ),
        )
        await _get_or_create(
            session,
            WebhookSession,
            select(WebhookSession).where(
                WebhookSession.user_id == user.id,
                WebhookSession.organization_id == organization.id,
            ),
            lambda: WebhookSession(
                user_id=user.id,
                organization_id=organization.id,
                status="active",
                expires_at=now + timedelta(days=1),
            ),
        )
    return user


async def _get_or_create(session, model, statement, factory):
    value = (await session.execute(statement)).scalars().first()
    if value is None:
        value = factory()
        session.add(value)
        await session.flush()
    return value


async def seed() -> dict[str, dict[str, str]]:
    hasher = Argon2PasswordHasher()
    now = datetime.now(timezone.utc)
    result: dict[str, dict[str, str]] = {}
    async with session_factory() as session:
        async with session.begin():
            platform_admin = await _get_or_create(
                session,
                User,
                select(User).where(User.username == "local-platform-admin"),
                lambda: User(
                    username="local-platform-admin",
                    display_name="本機平台管理員",
                    password_hash=hasher.hash("local-only-password"),
                    platform_role="PLATFORM_ADMIN",
                    status="active",
                ),
            )
            platform_admin.display_name = "本機平台管理員"
            platform_admin.platform_role = "PLATFORM_ADMIN"
            platform_admin.status = "active"
            result["PLATFORM"] = {
                "username": platform_admin.username,
                "role": platform_admin.platform_role,
            }
            disabled_platform_admin = await _get_or_create(
                session,
                User,
                select(User).where(User.username == "local-platform-admin-disabled"),
                lambda: User(
                    username="local-platform-admin-disabled",
                    display_name="本機已停用平台管理員",
                    password_hash=hasher.hash("local-only-password"),
                    platform_role="PLATFORM_ADMIN",
                    status="disabled",
                ),
            )
            disabled_platform_admin.display_name = "本機已停用平台管理員"
            disabled_platform_admin.platform_role = "PLATFORM_ADMIN"
            disabled_platform_admin.status = "disabled"
            result["PLATFORM_DISABLED"] = {
                "username": disabled_platform_admin.username,
                "role": disabled_platform_admin.platform_role,
            }
            for org_code, org_name in (("ORG-A", "虛構收容所 A"), ("ORG-B", "虛構收容所 B")):
                organization = await _get_or_create(
                    session,
                    Organization,
                    select(Organization).where(Organization.code == org_code),
                    lambda org_code=org_code, org_name=org_name: Organization(
                        code=org_code, name=org_name, status="active"
                    ),
                )
                organization.status = "active"
                policy = await _get_or_create(
                    session,
                    OrganizationVolunteerAccessPolicy,
                    select(OrganizationVolunteerAccessPolicy).where(
                        OrganizationVolunteerAccessPolicy.organization_id == organization.id
                    ),
                    lambda organization=organization: OrganizationVolunteerAccessPolicy(
                        organization_id=organization.id,
                        applications_enabled=True,
                        default_grant_duration_hours=168,
                    ),
                )
                policy.applications_enabled = org_code != "ORG-B"
                policy.default_grant_duration_hours = 72 if org_code == "ORG-A" else 168
                raw_entry_reference = f"local-volunteer-entry-{org_code.lower()}-" + "a" * 48
                entry_digest = hashlib.sha256(raw_entry_reference.encode()).hexdigest()
                await _get_or_create(
                    session,
                    ShelterVolunteerEntryReference,
                    select(ShelterVolunteerEntryReference).where(
                        ShelterVolunteerEntryReference.token_digest == entry_digest
                    ),
                    lambda organization=organization, entry_digest=entry_digest: (
                        ShelterVolunteerEntryReference(
                            organization_id=organization.id,
                            token_digest=entry_digest,
                            status="active",
                            issued_by_user_id=platform_admin.id,
                        )
                    ),
                )
                area = await _get_or_create(
                    session,
                    ShelterArea,
                    select(ShelterArea).where(
                        ShelterArea.organization_id == organization.id,
                        ShelterArea.name == f"MVP Cage {org_code[-1]}",
                    ),
                    lambda organization=organization, org_code=org_code: ShelterArea(
                        organization_id=organization.id,
                        name=f"MVP Cage {org_code[-1]}",
                        area_type="cage",
                        status="active",
                    ),
                )
                animal = await _get_or_create(
                    session,
                    Animal,
                    select(Animal).where(
                        Animal.organization_id == organization.id,
                        Animal.shelter_number == "VAAAG114080610",
                    ),
                    lambda organization=organization, area=area: Animal(
                        organization_id=organization.id,
                        name="小黑",
                        shelter_number="VAAAG114080610",
                        area_id=area.id,
                        status="active",
                    ),
                )
                animal.status = "active"
                animal.area_id = area.id
                staff_username = f"local-staff-{org_code[-1].lower()}"
                volunteer_username = f"local-volunteer-{org_code[-1].lower()}"
                staff = await _get_or_create(
                    session,
                    User,
                    select(User).where(User.username == staff_username),
                    lambda staff_username=staff_username, org_code=org_code: User(
                        username=staff_username,
                        display_name=f"本機工作人員 {org_code[-1]}",
                        password_hash=hasher.hash("local-only-password"),
                        status="active",
                    ),
                )
                volunteer = await _get_or_create(
                    session,
                    User,
                    select(User).where(User.username == volunteer_username),
                    lambda volunteer_username=volunteer_username, org_code=org_code: User(
                        username=volunteer_username,
                        display_name=f"本機志工 {org_code[-1]}",
                        password_hash=hasher.hash("local-only-password"),
                        status="active",
                    ),
                )
                for user, role in ((staff, "STAFF"), (volunteer, "VOLUNTEER")):
                    membership = await _get_or_create(
                        session,
                        OrganizationMembership,
                        select(OrganizationMembership).where(
                            OrganizationMembership.organization_id == organization.id,
                            OrganizationMembership.user_id == user.id,
                        ),
                        lambda user=user, role=role, organization=organization: (
                            OrganizationMembership(
                                organization_id=organization.id,
                                user_id=user.id,
                                role=role,
                                status="active",
                                valid_from=now - timedelta(hours=1)
                                if role == "VOLUNTEER"
                                else None,
                                expires_at=now + timedelta(days=7) if role == "VOLUNTEER" else None,
                            )
                        ),
                    )
                    membership.role = role
                    membership.status = "active"
                    if role == "VOLUNTEER":
                        membership.valid_from = now - timedelta(hours=1)
                        membership.expires_at = now + timedelta(days=7)
                        volunteer_membership = membership
                approved_application = await _get_or_create(
                    session,
                    VolunteerApplication,
                    select(VolunteerApplication).where(
                        VolunteerApplication.organization_id == organization.id,
                        VolunteerApplication.user_id == volunteer.id,
                        VolunteerApplication.status == "approved",
                    ),
                    lambda organization=organization, volunteer=volunteer, staff=staff: (
                        VolunteerApplication(
                            organization_id=organization.id,
                            user_id=volunteer.id,
                            status="approved",
                            source_channel="management",
                            submitted_at=now - timedelta(hours=2),
                            decided_at=now - timedelta(hours=1),
                            decided_by_user_id=staff.id,
                        )
                    ),
                )

                def _active_grant_factory(
                    organization=organization,
                    volunteer=volunteer,
                    staff=staff,
                    volunteer_membership=volunteer_membership,
                    approved_application=approved_application,
                    policy=policy,
                ):
                    return VolunteerAccessGrant(
                        organization_id=organization.id,
                        user_id=volunteer.id,
                        membership_id=volunteer_membership.id,
                        application_id=approved_application.id,
                        status="active",
                        valid_from=volunteer_membership.valid_from,
                        expires_at=volunteer_membership.expires_at,
                        approved_at=now - timedelta(hours=1),
                        approved_by_user_id=staff.id,
                        policy_version_used=policy.version,
                        duration_hours_used=168,
                    )

                await _get_or_create(
                    session,
                    VolunteerAccessGrant,
                    select(VolunteerAccessGrant).where(
                        VolunteerAccessGrant.application_id == approved_application.id
                    ),
                    _active_grant_factory,
                )
                if org_code == "ORG-A":
                    for fixture_state in (
                        "rejected",
                        "future",
                        "expired",
                        "revoked",
                        "disabled_user",
                    ):
                        await _seed_application_and_grant_state(
                            session,
                            organization=organization,
                            approver=staff,
                            policy=policy,
                            state=fixture_state,
                            now=now,
                        )
                else:
                    await _seed_application_and_grant_state(
                        session,
                        organization=organization,
                        approver=staff,
                        policy=policy,
                        state="future",
                        now=now,
                    )
                if org_code == "ORG-A":
                    shelter_admin = await _get_or_create(
                        session,
                        User,
                        select(User).where(User.username == "local-shelter-admin-a"),
                        lambda: User(
                            username="local-shelter-admin-a",
                            display_name="本機收容所管理員 A",
                            password_hash=hasher.hash("local-only-password"),
                            status="active",
                        ),
                    )
                    shelter_admin.display_name = "本機收容所管理員 A"
                    shelter_admin.status = "active"
                    shelter_admin_membership = await _get_or_create(
                        session,
                        OrganizationMembership,
                        select(OrganizationMembership).where(
                            OrganizationMembership.organization_id == organization.id,
                            OrganizationMembership.user_id == shelter_admin.id,
                        ),
                        lambda shelter_admin=shelter_admin, organization=organization: (
                            OrganizationMembership(
                                organization_id=organization.id,
                                user_id=shelter_admin.id,
                                role="SHELTER_ADMIN",
                                status="active",
                            )
                        ),
                    )
                    shelter_admin_membership.role = "SHELTER_ADMIN"
                    shelter_admin_membership.status = "active"
                active_session = await _get_or_create(
                    session,
                    SessionRecord,
                    select(SessionRecord).where(
                        SessionRecord.user_id == volunteer.id,
                        SessionRecord.active_organization_id == organization.id,
                        SessionRecord.status == "active",
                    ),
                    lambda volunteer=volunteer, organization=organization: SessionRecord(
                        user_id=volunteer.id,
                        active_organization_id=organization.id,
                        status="active",
                        expires_at=now + timedelta(days=7),
                    ),
                )
                line_user_id = f"Ulocal-volunteer-{org_code[-1]}"
                line_binding = await _get_or_create(
                    session,
                    LineUserBinding,
                    select(LineUserBinding).where(LineUserBinding.line_user_id == line_user_id),
                    lambda line_user_id=line_user_id, volunteer=volunteer: LineUserBinding(
                        line_user_id=line_user_id,
                        user_id=volunteer.id,
                        status="active",
                    ),
                )
                await _seed_failed_notifications(
                    session,
                    organization=organization,
                    volunteer=volunteer,
                    line_binding=line_binding,
                    now=now,
                )
                if org_code == "ORG-A":
                    await _seed_pending_applicant_set(
                        session,
                        organization=organization,
                        prefix="manual",
                        count=100,
                        now=now,
                    )
                    await _seed_pending_applicant_set(
                        session,
                        organization=organization,
                        prefix="all-filtered",
                        count=1200,
                        now=now,
                    )
                raw_qr_token = f"local-mvp-qr-{org_code}"
                await _get_or_create(
                    session,
                    AnimalQrCode,
                    select(AnimalQrCode).where(AnimalQrCode.animal_id == animal.id),
                    lambda organization=organization, animal=animal, raw_qr_token=raw_qr_token: (
                        AnimalQrCode(
                            organization_id=organization.id,
                            animal_id=animal.id,
                            token_digest=hashlib.sha256(raw_qr_token.encode()).hexdigest(),
                            status="active",
                            revoked=False,
                        )
                    ),
                )
                scope = await _get_or_create(
                    session,
                    DailyReportableScope,
                    select(DailyReportableScope).where(
                        DailyReportableScope.organization_id == organization.id,
                        DailyReportableScope.animal_id == animal.id,
                        DailyReportableScope.volunteer_user_id == volunteer.id,
                    ),
                    lambda organization=organization, animal=animal, volunteer=volunteer: (
                        DailyReportableScope(
                            organization_id=organization.id,
                            animal_id=animal.id,
                            volunteer_user_id=volunteer.id,
                            starts_at=now - timedelta(days=1),
                            ends_at=now + timedelta(days=1),
                            status="active",
                        )
                    ),
                )
                scope.starts_at = now - timedelta(days=1)
                scope.ends_at = now + timedelta(days=1)

                await seed_vocabulary(session)
                result[org_code] = {
                    "organization_id": str(organization.id),
                    "staff_username": staff.username,
                    "volunteer_username": volunteer.username,
                    "session_id": str(active_session.id),
                    "line_user_id": line_user_id,
                    "qr_token": raw_qr_token,
                    "volunteer_entry_reference": raw_entry_reference,
                    "animal_id": str(animal.id),
                    "unknown_identity_token": f"local-id-token:unknown-{org_code.lower()}",
                    "manual_batch_fixture_count": "100" if org_code == "ORG-A" else "0",
                    "all_filtered_fixture_count": "1200" if org_code == "ORG-A" else "0",
                }
                if org_code == "ORG-A":
                    result[org_code]["shelter_admin_username"] = shelter_admin.username
            disabled_organization = await _get_or_create(
                session,
                Organization,
                select(Organization).where(Organization.code == "ORG-DISABLED"),
                lambda: Organization(
                    code="ORG-DISABLED",
                    name="停用收容所 Fixture",
                    status="suspended",
                ),
            )
            disabled_organization.status = "suspended"
            disabled_policy = await _get_or_create(
                session,
                OrganizationVolunteerAccessPolicy,
                select(OrganizationVolunteerAccessPolicy).where(
                    OrganizationVolunteerAccessPolicy.organization_id == disabled_organization.id
                ),
                lambda: OrganizationVolunteerAccessPolicy(
                    organization_id=disabled_organization.id,
                    applications_enabled=False,
                    default_grant_duration_hours=168,
                ),
            )
            disabled_org_user = await _seed_application_and_grant_state(
                session,
                organization=disabled_organization,
                approver=staff,
                policy=disabled_policy,
                state="future",
                now=now,
            )
            stale_session = await _get_or_create(
                session,
                SessionRecord,
                select(SessionRecord).where(
                    SessionRecord.user_id == disabled_org_user.id,
                    SessionRecord.active_organization_id == disabled_organization.id,
                ),
                lambda: SessionRecord(
                    user_id=disabled_org_user.id,
                    active_organization_id=disabled_organization.id,
                    status="active",
                    expires_at=now + timedelta(days=1),
                ),
            )
            await _get_or_create(
                session,
                WebhookSession,
                select(WebhookSession).where(
                    WebhookSession.user_id == disabled_org_user.id,
                    WebhookSession.organization_id == disabled_organization.id,
                ),
                lambda: WebhookSession(
                    user_id=disabled_org_user.id,
                    organization_id=disabled_organization.id,
                    status="active",
                    expires_at=now + timedelta(days=1),
                ),
            )
            result["ORG-DISABLED"] = {
                "organization_id": str(disabled_organization.id),
                "stale_session_id": str(stale_session.id),
            }
    return result


def main() -> None:
    print(json.dumps(asyncio.run(seed()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
